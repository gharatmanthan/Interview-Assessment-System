from fastapi import APIRouter
from api.schemas import DeviceInfo

router = APIRouter()


@router.get("", response_model=list[DeviceInfo])
def list_devices():
    devices = []

    try:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                devices.append(DeviceInfo(name=d["name"], index=i, device_class="microphone"))
    except Exception:
        pass

    try:
        import cv2
        import os
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        try:
            for i in range(5):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    devices.append(DeviceInfo(name=f"Camera {i}", index=i, device_class="camera"))
                    cap.release()
        finally:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
    except Exception:
        pass

    return devices
