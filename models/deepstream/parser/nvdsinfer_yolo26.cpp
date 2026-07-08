/* Custom DeepStream bbox parser for Ultralytics YOLO26 end-to-end ONNX export.
 *
 * YOLO26 is NMS-free: the model's single output tensor already contains final
 * detections, shape [batch, 300, 6] where each row = x1,y1,x2,y2,score,class
 * in network-input (letterboxed) pixel coordinates. So this parser only
 * thresholds and copies — set cluster-mode=4 (none) in the nvinfer config.
 *
 * Build (inside the DeepStream container):
 *   g++ -shared -fPIC -o libnvdsparser_yolo26.so nvdsinfer_yolo26.cpp \
 *       -I/opt/nvidia/deepstream/deepstream/sources/includes \
 *       -I/usr/local/cuda/include
 */
#include "nvdsinfer_custom_impl.h"

#include <algorithm>
#include <vector>

extern "C" bool NvDsInferParseYolo26(
    std::vector<NvDsInferLayerInfo> const& outputLayersInfo,
    NvDsInferNetworkInfo const& networkInfo,
    NvDsInferParseDetectionParams const& detectionParams,
    std::vector<NvDsInferParseObjectInfo>& objectList)
{
    if (outputLayersInfo.empty() || outputLayersInfo[0].buffer == nullptr)
        return false;

    const NvDsInferLayerInfo& layer = outputLayersInfo[0];
    // Batch dim is stripped by nvinfer: dims are [300, 6].
    const int rows = layer.inferDims.numDims >= 1 ? layer.inferDims.d[0] : 0;
    const int cols = layer.inferDims.numDims >= 2 ? layer.inferDims.d[1] : 0;
    if (cols != 6)
        return false;

    const float* data = reinterpret_cast<const float*>(layer.buffer);
    const float netW = static_cast<float>(networkInfo.width);
    const float netH = static_cast<float>(networkInfo.height);
    const int numClasses = static_cast<int>(detectionParams.numClassesConfigured);

    objectList.reserve(rows);
    for (int i = 0; i < rows; ++i) {
        const float* r = data + static_cast<size_t>(i) * 6;
        const float score = r[4];
        const int cls = static_cast<int>(r[5]);
        if (cls < 0 || cls >= numClasses)
            continue;
        const float thr = detectionParams.perClassPreclusterThreshold.empty()
            ? 0.25f : detectionParams.perClassPreclusterThreshold[cls];
        if (score < thr)
            continue;

        const float x1 = std::min(std::max(r[0], 0.f), netW);
        const float y1 = std::min(std::max(r[1], 0.f), netH);
        const float x2 = std::min(std::max(r[2], 0.f), netW);
        const float y2 = std::min(std::max(r[3], 0.f), netH);
        if (x2 <= x1 || y2 <= y1)
            continue;

        NvDsInferParseObjectInfo obj{};
        obj.left = x1;
        obj.top = y1;
        obj.width = x2 - x1;
        obj.height = y2 - y1;
        obj.detectionConfidence = score;
        obj.classId = static_cast<unsigned int>(cls);
        objectList.push_back(obj);
    }
    return true;
}

/* Sanity-check the exported symbol matches the expected prototype. */
CHECK_CUSTOM_PARSE_FUNC_PROTOTYPE(NvDsInferParseYolo26);
