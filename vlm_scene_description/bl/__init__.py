# Business logic layer.
# Import only from models/. No FastAPI types, no HTTP concepts.
# Heavy dependencies (nuscenes-devkit, transformers, torch) stay behind lazy
# imports inside methods so this layer stays fast and easily testable with fakes.
