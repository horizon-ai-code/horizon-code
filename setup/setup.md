# Horizon Environment Setup Guide

This document outlines the system requirements and installation steps to set up the **Horizon** development environment. This setup is designed for Linux systems with NVIDIA GPUs and specifically handles the custom compilation of `llama-cpp-python` with CUDA support.

## 1. System Prerequisites

Before running the installation scripts, ensure the host machine meets the following requirements.

### NVIDIA Drivers

Ensure proprietary NVIDIA drivers are installed and functioning.

```bash
nvidia-smi

```

_Expected Output:_ You should see your GPU name, driver version, and CUDA version.

### CUDA Toolkit (nvcc)

The installation script requires the CUDA compiler (`nvcc`) to build the Python bindings.

- **Default Path:** `/usr/local/cuda/bin/nvcc`
- **Verification:**

```bash
/usr/local/cuda/bin/nvcc --version

```

If `nvcc` is not found, install the CUDA Toolkit (version 11.8 or 12.x is recommended). If your CUDA installation is in a non-standard location, you must edit the `CUDACXX` path in `create_env.sh`.

### Conda Distribution

A Conda manager is required to handle the virtual environment and isolated compilers.

- **Verification:**

```bash
conda --version

```

If missing, install Miniconda or Anaconda.

---

## 2. Installation Steps

### Step 1: Prepare Scripts

Ensure `create_env.sh` and `dl_models.sh` are located in your project root. Grant execution permissions to both scripts:

```bash
chmod +x create_env.sh dl_models.sh

```

### Step 2: Build Environment

Run the environment creation script. This script performs the following actions:

1. Creates the `horizon_env` Conda environment with Python 3.10.
2. Installs isolated GCC/G++ 12 compilers (to ensure binary compatibility).
3. Forces the compilation of `llama-cpp-python` with the `-DGGML_CUDA=on` flag.

```bash
./create_env.sh

```

_Note: This process may take several minutes depending on download speeds and compilation time._

### Step 3: Download Models

Once the environment is built, activate it and run the model downloader script.

```bash
conda activate horizon_env
./dl_models.sh

```

---

## 3. Verification

To verify that the GPU is being utilized for inference, look for specific initialization logs when running your Python scripts.

**Successful GPU Offload Indicators:**
When loading a model, the terminal output should contain lines similar to:

- `ggml_cuda_init: found 1 CUDA devices:`
- `BLAS = 1`
- `llm_load_tensors: offloaded XX/XX layers to GPU`

**Failure Indicators (CPU Fallback):**
If compilation failed, you will see:

- `BLAS = 0`
- `0 layers offloaded to GPU`

### Manual Verification Command

You can run this Python command inside the environment to check build status:

```bash
python -c "import llama_cpp; print('GPU Enabled' if llama_cpp.llama_backend_free else 'CPU Only')"

```
