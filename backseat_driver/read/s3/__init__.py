"""The dataset in an S3-compatible bucket: the layer that lets distributed workers read without a shared disk.

Everything here implements a `read/` port (`ImageStore`, `SceneLoader`) over the bucket, plus the one-time
`DatasetUploader` that copies a local dataset into it. Nothing in the read-process-write core imports this package.
"""
