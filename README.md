```bash
python models/clip_embedder/export.py
```


```bash 
docker run --gpus all --rm -it \
  -p8001:8001 -p8002:8002 \
  -v ${PWD}/models:/models \
  nvcr.io/nvidia/tritonserver:23.10-py3 \
  tritonserver --model-repository=/models
```