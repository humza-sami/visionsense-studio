"""Mixed-workload scenario benchmark: several camera GROUPS, each with its own model
and its own target detection fps, sharing one GPU — the realistic way to pack a box
(e.g. attendance cameras on a fast model @ high fps + fire cameras on a big model @ 1 fps).

Writes one summary row per scenario to combinations.csv and prints per-group detail.

  python scripts/benchmark_mixed.py <scenario|all> <seconds> <relay_url> <csv>
"""
from __future__ import annotations
import csv, json, os, statistics, subprocess, sys, time

from src.capture.frame_buffer import LatestFrameBuffer
from src.capture.rtsp_worker import CameraWorker
from src.config import CameraConfig, CaptureConfig, ModelConfig
from src.inference.engine import Detector

ENG = {
    "n": ("models/yolo26n.engine","models/yolo26n.pt","yolo26n"),
    "s": ("models/yolo26s.engine","models/yolo26s.pt","yolo26s"),
    "m": ("models/yolo26m.engine","models/yolo26m.pt","yolo26m"),
    "l": ("models/yolo26l.engine","models/yolo26l.pt","yolo26l"),
    "x": ("models/yolo26x.engine","models/yolo26x.pt","yolo26x"),
}
# scenario = list of groups: (label, count, model_key, input_fps, target_det_fps)
SCENARIOS = {
    "S1_warehouse": [("attendance",10,"m",15,10.0), ("fire",5,"l",5,1.0)],
    "S2_retail":    [("people",8,"s",12,8.0),       ("theft",4,"l",15,10.0)],
    "S3_safety":    [("ppe",12,"m",10,3.0),          ("fire",3,"x",5,1.0)],
    "S4_mixedfps":  [("live",5,"m",25,15.0),         ("periodic",10,"m",5,3.0)],
}
COLUMNS = ["scenario","total_cameras","groups","gpu_util_avg","gpu_util_peak",
           "nvdec_util_avg","vram_used_MB_peak","vram_free_MB","cpu_util_avg","ram_used_MB",
           "predicted_infer_ms_per_s","notes"]

def nv(q):
    try: return float(subprocess.check_output(["nvidia-smi",f"--query-gpu={q}","--format=csv,noheader,nounits"],text=True).split("\n")[0])
    except: return -1.0
def cpu_pct(iv=0.4):
    def s():
        v=list(map(int,open("/proc/stat").readline().split()[1:8])); return sum(v),v[3]+v[4]
    a,ai=s(); time.sleep(iv); b,bi=s(); return 0.0 if b==a else round(100*(1-(bi-ai)/(b-a)),1)
def ram_mb():
    m={}
    for ln in open("/proc/meminfo"):
        k,v=ln.split(":"); m[k]=int(v.strip().split()[0])
    return (m["MemTotal"]-m["MemAvailable"])//1024

# amortized ms/frame per model (measured, 3070 Ti @640) — for the predicted load column
MS_PER_FRAME = {"yolo26n":5.5,"yolo26s":6.5,"yolo26m":8.0,"yolo26l":10.4,"yolo26x":20.0}

def run_scenario(name, groups, secs, url, csv_path):
    cap_cfg = CaptureConfig(backend="gstreamer", rtsp_transport="tcp", codec="h265")
    buf = LatestFrameBuffer()
    workers=[]; cam_i=0
    detectors={}  # model_key -> Detector
    G=[]
    for (label,count,mk,ifps,dfps) in groups:
        if mk not in detectors:
            eng,wt,nm = ENG[mk]
            detectors[mk] = Detector(ModelConfig(weights=wt, engine=eng, imgsz=640, conf=0.25,
                                     iou=0.45, device="cuda:0", classes=None, max_batch=count if count>16 else 16))
        cams=[]
        for _ in range(count):
            cam_i+=1; cid=f"cam{cam_i:02d}"
            cams.append(cid)
            w=CameraWorker(CameraConfig(id=cid,url=url,enabled=True), buf, cap_cfg); w.start(); workers.append(w)
        G.append({"label":label,"cams":cams,"det":detectors[mk],"model":ENG[mk][2],
                  "ifps":ifps,"dfps":dfps,"last":0.0,"n":0,"bs":[]})
    print(f"[{name}] {len(workers)} cameras, {len(detectors)} models — warming up 15s")
    time.sleep(15)

    gpu=[];dec=[];vram=[];cpu=[]
    t0=time.monotonic(); end=t0+secs; nextsample=t0
    while time.monotonic()<end:
        now=time.monotonic()
        for g in G:
            if now-g["last"] >= 1.0/g["dfps"]:
                frames=[buf.get(c) for c in g["cams"]]; frames=[f for f in frames if f is not None]
                if frames:
                    g["det"].detect_batch(frames)
                    g["last"]=now; g["n"]+=1; g["bs"].append(len(frames))
        if now>=nextsample:
            gpu.append(nv("utilization.gpu")); dec.append(nv("utilization.decoder"))
            vram.append(nv("memory.used")); cpu.append(cpu_pct(0.3)); nextsample=now+1.5
        time.sleep(0.002)
    dur=time.monotonic()-t0
    for w in workers: w.stop()

    a=lambda x: round(statistics.mean(x),1) if x else 0.0
    pk=lambda x: round(max(x),1) if x else 0.0
    vtot=int(nv("memory.total"))
    pred=sum(len(g["cams"])*g["dfps"]*MS_PER_FRAME[g["model"]] for g in G)
    gdesc=[{"label":g["label"],"model":g["model"],"cams":len(g["cams"]),
            "target_fps":g["dfps"],"achieved_fps":round(g["n"]/dur,2),
            "avg_batch":round(statistics.mean(g["bs"]),1) if g["bs"] else 0} for g in G]
    row={"scenario":name,"total_cameras":len(workers),"groups":json.dumps(gdesc),
         "gpu_util_avg":a(gpu),"gpu_util_peak":pk(gpu),"nvdec_util_avg":a(dec),
         "vram_used_MB_peak":pk(vram),"vram_free_MB":round(vtot-pk(vram)),
         "cpu_util_avg":a(cpu),"ram_used_MB":ram_mb(),
         "predicted_infer_ms_per_s":round(pred),"notes":""}
    new=not os.path.exists(csv_path)
    with open(csv_path,"a",newline="") as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS)
        if new: w.writeheader()
        w.writerow(row)
    print(f"\n[{name}] GPU {a(gpu)}%/{pk(gpu)}pk · NVDEC {a(dec)}% · VRAM {pk(vram)}MB · CPU {a(cpu)}% · predicted {round(pred)} ms/s")
    for g in gdesc: print(f"   {g['label']:11s} {g['model']} ×{g['cams']:2d}  target {g['target_fps']}fps → got {g['achieved_fps']}fps  batch {g['avg_batch']}")

def main():
    which=sys.argv[1] if len(sys.argv)>1 else "all"
    secs=int(sys.argv[2]) if len(sys.argv)>2 else 30
    url=sys.argv[3] if len(sys.argv)>3 else "rtsp://127.0.0.1:8554/live"
    csv_path=sys.argv[4] if len(sys.argv)>4 else "combinations.csv"
    if which=="all" and os.path.exists(csv_path): os.remove(csv_path)
    # single scenario runs in-process (isolated by the subprocess call below for clean VRAM)
    if which!="all":
        run_scenario(which, SCENARIOS[which], secs, url, csv_path); sys.stdout.flush(); os._exit(0)
    for nm in list(SCENARIOS):
        subprocess.run([sys.executable, __file__, nm, str(secs), url, csv_path],
                       env={**os.environ,"PYTHONPATH":os.getcwd()}); time.sleep(4)
    print(f"\ncombinations CSV: {csv_path}")

if __name__=="__main__":
    sys.exit(main())
