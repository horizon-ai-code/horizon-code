# ==========================================
# MANUAL INSTALLATION (GPU FORCE BUILD)
# Run these commands in the terminal after: conda activate horizon_env
# ==========================================
#
# # 1. Point to System CUDA
export CUDACXX=/usr/local/cuda/bin/nvcc
#
# # 2. Point to the "Time Capsule" Compilers (Conda)
export CC=$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-gcc
export CXX=$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-g++
#
# # 3. Force the Compile
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir

pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir
