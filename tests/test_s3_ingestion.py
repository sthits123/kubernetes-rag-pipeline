import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.ingestion import processor


class FakeS3:
    def get_paginator(self, operation_name):
        if operation_name != "list_objects_v2":
            raise AssertionError(operation_name)
        return self

    def paginate(self, **kwargs):
        self.list_request = kwargs
        return [{"Contents": [{"Key": "documents/guide.txt"}]}]

    def download_file(self, bucket, key, destination):
        with open(destination, "w", encoding="utf-8") as file:
            file.write("Kubernetes uses declarative configuration.")


class S3IngestionTests(unittest.TestCase):
    def test_s3_prefix_downloads_and_indexes_documents(self):
        s3 = FakeS3()
        aws_settings = SimpleNamespace(
            RAG_PROVIDER="aws",
            AWS_REGION="us-east-1",
            S3_BUCKET="private-documents",
            S3_DOCUMENT_PREFIX="documents",
            validate=lambda: None,
        )
        indexed_chunks = []

        def capture_chunks(chunks):
            indexed_chunks.extend(chunks)
            return len(chunks)

        with (
            patch.object(processor, "settings", aws_settings),
            patch("boto3.client", return_value=s3),
            patch.object(processor, "index_chunks", side_effect=capture_chunks),
        ):
            result = processor.ingest_s3_prefix("documents")

        self.assertEqual(result, 1)
        self.assertEqual(
            s3.list_request,
            {"Bucket": "private-documents", "Prefix": "documents/"},
        )
        self.assertEqual(indexed_chunks[0]["source"], "guide.txt")
        self.assertIn("Kubernetes uses declarative", indexed_chunks[0]["text"])


if __name__ == "__main__":
    unittest.main()
