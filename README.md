```bash
python -m alembic revision --autogenerate -m "init"
```

```bash
python models/embedder/export.py
```


```bash 
docker run --gpus all --rm -it -v ${PWD}/models:/models -p8000:8000 -p8001:8001 -p8002:8002 nvcr.io/nvidia/tritonserver:23.10-py3 tritonserver --model-repository=/models
```