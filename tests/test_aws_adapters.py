import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.gateway import client as gateway_client
from app.services.retrieval import embedding
from app.services.retrieval import qdrant_service


class FakeOpenSearch:
    def __init__(self):
        self.index = SimpleNamespace(exists=lambda index: True)
        self.indices = self.index
        self.search_response = {
            "hits": {
                "hits": [
                    {
                        "_score": 0.9,
                        "_source": {"text": "retrieved chunk", "source": "guide.md"},
                    }
                ]
            }
        }

    def search(self, **kwargs):
        return self.search_response


class AwsVectorAdapterTests(unittest.TestCase):
    def test_bedrock_models_use_configured_ids_and_region(self):
        aws_settings = SimpleNamespace(
            RAG_PROVIDER="aws",
            AWS_REGION="us-east-1",
            BEDROCK_CHAT_MODEL_ID="amazon.nova-lite-v1:0",
            BEDROCK_GUARDRAIL_MODEL_ID="amazon.nova-lite-v1:0",
            BEDROCK_EMBEDDING_MODEL_ID="amazon.titan-embed-text-v2:0",
            BEDROCK_EMBEDDING_DIMENSIONS=512,
            validate=lambda: None,
        )
        with (
            patch.object(gateway_client, "settings", aws_settings),
            patch.object(embedding, "settings", aws_settings),
        ):
            gateway_client.get_langchain_llm.cache_clear()
            embedding._embedding_client.cache_clear()
            try:
                chat_model = gateway_client.get_langchain_llm()
                embedding_model = embedding._embedding_client()
            finally:
                gateway_client.get_langchain_llm.cache_clear()
                embedding._embedding_client.cache_clear()

        self.assertEqual(chat_model.model, "amazon.nova-lite-v1:0")
        self.assertEqual(chat_model.region_name, "us-east-1")
        self.assertEqual(embedding_model.model_id, "amazon.titan-embed-text-v2:0")
        self.assertEqual(embedding_model.dimensions, 512)

    def test_search_maps_opensearch_hits(self):
        client = FakeOpenSearch()
        aws_settings = SimpleNamespace(
            RAG_PROVIDER="aws",
            OPENSEARCH_ENDPOINT="https://search.example.us-east-1.aoss.amazonaws.com",
            OPENSEARCH_INDEX="kubernetes-rag",
        )
        with (
            patch.object(qdrant_service, "settings", aws_settings),
            patch.object(qdrant_service, "embed_query", return_value=[0.1, 0.2]),
            patch.object(qdrant_service, "_get_opensearch_client", return_value=client),
        ):
            results = qdrant_service.search_enterprise_knowledge("test query", limit=3)

        self.assertEqual(
            results,
            [{"content": "retrieved chunk", "source": "guide.md", "score": 0.9}],
        )

    def test_index_chunks_embeds_and_bulk_indexes_with_stable_ids(self):
        client = FakeOpenSearch()
        aws_settings = SimpleNamespace(
            RAG_PROVIDER="aws",
            OPENSEARCH_INDEX="kubernetes-rag",
        )
        chunks = [
            {"id": "stable-id-1", "text": "first chunk", "source": "one.txt"},
            {"id": "stable-id-2", "text": "second chunk", "source": "two.txt"},
        ]
        captured = {}

        def capture_bulk(client_arg, actions, **kwargs):
            captured["client"] = client_arg
            captured["actions"] = list(actions)

        with (
            patch.object(qdrant_service, "settings", aws_settings),
            patch.object(
                qdrant_service,
                "embed_texts",
                return_value=[[0.1, 0.2], [0.3, 0.4]],
            ),
            patch.object(qdrant_service, "_ensure_opensearch_index") as ensure_index,
            patch.object(qdrant_service, "_get_opensearch_client", return_value=client),
            patch("opensearchpy.helpers.bulk", side_effect=capture_bulk),
        ):
            indexed = qdrant_service.index_chunks(chunks)

        self.assertEqual(indexed, 2)
        ensure_index.assert_called_once_with(2)
        self.assertEqual(captured["client"], client)
        self.assertEqual(
            [action["_id"] for action in captured["actions"]],
            ["stable-id-1", "stable-id-2"],
        )
        self.assertEqual(captured["actions"][0]["_source"]["embedding"], [0.1, 0.2])


if __name__ == "__main__":
    unittest.main()
