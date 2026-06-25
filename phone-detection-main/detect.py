from ultralytics import YOLO
import cv2
from flask import Flask, Response

app = Flask(__name__)
model = YOLO("yolo26n.pt")  # auto-downloads on first run, persists in ./


def generate_frames():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        results = model(frame, classes=[0, 67], verbose=False)  # 0=person, 67=cell phone
        annotated = results[0].plot()
        _, buffer = cv2.imencode('.jpg', annotated)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
               + buffer.tobytes() + b'\r\n')


@app.route('/stream')
def stream():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
