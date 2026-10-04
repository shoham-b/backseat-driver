"""Stage 1, read: get the scenes and their images.

`SceneLoader` turns a dataset into `SceneKeyframe`s and `ImageStore` hands out an image's bytes. This package holds
the simple core, a loader and a store that read a dataset on local disk. `read/s3/` is the layer that puts the
dataset in an S3-compatible bucket instead, for workers that share no disk.
"""
