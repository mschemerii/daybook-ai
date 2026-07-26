from src.runtime.hardware import _classify_gpu


def test_gpu_vendor_classification():
    assert _classify_gpu("NVIDIA GeForce RTX 3090") == ("NVIDIA", "CUDA")
    assert _classify_gpu("AMD Radeon RX 7900 XTX") == ("AMD", "Vulkan or ROCm")
    assert _classify_gpu("Intel Arc A770") == ("Intel", "Vulkan, SYCL, or OpenVINO")
    assert _classify_gpu("Apple M4 Max") == ("Apple", "Metal")


def test_unknown_device_falls_back_to_cpu():
    assert _classify_gpu("Generic display adapter") == (None, "CPU")
