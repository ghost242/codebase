"""
repository.py
=============

This module provides the EmbeddingRepository class responsible for MongoDB interactions.
It handles connection, index creation, bulk upsert storage, as well as update and delete
operations for embedding documents representing code components.
"""


import logging
from datetime import datetime
from typing import Dict, List, Optional, Union
from pymongo import MongoClient, ASCENDING, UpdateOne
from pymongo.database import Database
from bson import ObjectId

from codebase.code_indexer.models import ClassDocumentModel, FunctionDocumentModel


class EmbeddingRepository:
    """Handles MongoDB interactions for embedding storage, update, and deletion.

    This class establishes the MongoDB connection, creates necessary indexes, and
    performs bulk write operations for storing embedding documents. It also provides
    methods to update and delete documents, allowing the repository to reflect changes
    from the codebase.

    New collections are created dynamically based on the project name.
    """
    def __init__(
        self,
        mongo_uri: str,
        project_name: str,
        db_name: str = "code_embeddings",
        vector_dims: int = 384
    ):
        """
        Initializes the repository with collections based on the project name.

        Args:
            mongo_uri (str): MongoDB connection URI.
            project_name (str): Name of the project. Collections will be named as
                "<project_name>_classes" and "<project_name>_functions".
            db_name (str, optional): Database name. Defaults to "code_embeddings".
            vector_dims (int, optional): Dimensions of the embedding vectors. Defaults to 384.
        """
        self.client = MongoClient(mongo_uri)
        self.db: Database = self.client[db_name]
        # Create dynamic collection names based on project name.
        self.classes = self.db[f"{project_name}_classes"]
        self.functions = self.db[f"{project_name}_functions"]
        self.vector_dims = vector_dims
        self._ensure_indexes()
        self._create_vector_search_indexes()

    def _ensure_indexes(self):
        """Create standard indexes for the dynamic classes and functions collections."""
        self.classes.create_index([("package", ASCENDING), ("name", ASCENDING)], unique=True)
        self.classes.create_index("model")
        self.functions.create_index(
            [("package", ASCENDING), ("name", ASCENDING), ("parent_class_id", ASCENDING)],
            unique=True,
        )
        self.functions.create_index("parent_class_id")
        self.functions.create_index("type")
        self.functions.create_index("model")

    def _create_vector_search_indexes(self):
        """Create vector search indexes for the dynamic collections.

        Attempts to create indexes for vector search. If indexes already exist,
        a warning is logged.
        """
        try:
            self.db.command({
                "createIndexes": self.classes.name,
                "indexes": [
                    {
                        "name": "vector_search_class",
                        "key": {"embedding_vector": "vectorSearch"},
                        "vectorSearchOptions": {"dimension": self.vector_dims, "similarity": "cosine"},
                    }
                ],
            })
            self.db.command({
                "createIndexes": self.functions.name,
                "indexes": [
                    {
                        "name": "vector_search_function",
                        "key": {"embedding_vector": "vectorSearch"},
                        "vectorSearchOptions": {"dimension": self.vector_dims, "similarity": "cosine"},
                    }
                ],
            })
        except Exception as e:
            logging.warning(f"Vector search indexes might already exist: {e}")

    def upsert_document(self, filter_criteria: dict, document: dict) -> ObjectId:
        """
        Upserts a document in the appropriate collection based on its type.
        The filter_criteria should uniquely identify a document (e.g., using model, type, and name).
        If the document already exists, it is updated with the new data;
        otherwise, a new document is inserted.
        
        Args:
            filter_criteria (dict): The filter used to find the document.
            document (dict): The document data to upsert.
            
        Returns:
            ObjectId: The MongoDB ObjectId of the inserted/updated document.
            
        Raises:
            ValueError: If an unsupported document type is encountered.
        """
        # Select collection based on document type.
        doc_type = document.get("type")
        if doc_type == "class":
            collection = self.classes
        elif doc_type in ("function", "method"):
            collection = self.functions
        else:
            raise ValueError("Unsupported document type for upsert")

        now = datetime.now()
        document["updated_at"] = now
        # Preserve created_at if the document already exists.
        existing_doc = collection.find_one(filter_criteria)
        if existing_doc:
            document["created_at"] = existing_doc.get("created_at", now)
        else:
            document["created_at"] = now

        result = collection.update_one(filter_criteria, {"$set": document}, upsert=True)
        if result.upserted_id is not None:
            return result.upserted_id
        else:
            updated_doc = collection.find_one(filter_criteria)
            return updated_doc["_id"]

    def store_embeddings(
        self,
        embeddings: Dict[str, List[Union[ClassDocumentModel, FunctionDocumentModel]]],
        model: str
    ) -> Dict[str, ObjectId]:
        """Stores embedding documents in MongoDB using bulk upsert operations.

        Args:
            embeddings (Dict[str, List[Union[ClassDocumentModel, FunctionDocumentModel]]]):
                Dictionary containing lists of class and function documents.
            model (str): Identifier for the embedding model.

        Returns:
            Dict[str, ObjectId]: Mapping from entity names to their stored ObjectIds.
        """
        stored_ids = {}
        current_time = datetime.now()

        # Bulk upsert for class documents.
        class_ops = []
        for class_doc in embeddings.get("classes", []):
            class_doc.created_at = current_time
            class_doc.updated_at = current_time
            filter_criteria = {"package": class_doc.package, "name": class_doc.name}
            class_ops.append(
                UpdateOne(filter_criteria, {"$set": class_doc.model_dump(by_alias=True)}, upsert=True)
            )
            stored_ids[class_doc.name] = class_doc._id
        if class_ops:
            self.classes.bulk_write(class_ops)

        # Bulk upsert for function documents.
        function_ops = []
        for function_doc in embeddings.get("functions", []):
            function_doc.created_at = current_time
            function_doc.updated_at = current_time
            if function_doc.type == "method":
                filter_criteria = {
                    "package": function_doc.package,
                    "name": function_doc.name,
                    "parent_class_id": function_doc.parent_class_id,
                }
            else:
                filter_criteria = {
                    "package": function_doc.package,
                    "name": function_doc.name,
                    "parent_class_id": None,
                }
            function_ops.append(
                UpdateOne(filter_criteria, {"$set": function_doc.model_dump(by_alias=True)}, upsert=True)
            )
            stored_ids[function_doc.name] = function_doc._id
        if function_ops:
            self.functions.bulk_write(function_ops)

        return stored_ids

    def update_document(self, doc_type: str, filter_criteria: dict, update_data: dict) -> None:
        """Updates a single document in the specified collection.

        Args:
            doc_type (str): Type of document, either "class" or "function".
            filter_criteria (dict): Criteria to locate the document.
            update_data (dict): Data to update in the document.

        Raises:
            ValueError: If an invalid document type is provided.
        """
        if doc_type == "class":
            self.classes.update_one(filter_criteria, {"$set": update_data})
        elif doc_type == "function":
            self.functions.update_one(filter_criteria, {"$set": update_data})
        else:
            raise ValueError("Invalid document type. Must be 'class' or 'function'.")

    def delete_document(self, doc_type: str, filter_criteria: dict) -> int:
        """Deletes documents from the specified collection based on filter criteria.

        Args:
            doc_type (str): Type of document, either "class" or "function".
            filter_criteria (dict): Criteria to identify documents to delete.

        Returns:
            int: The number of documents deleted.

        Raises:
            ValueError: If an invalid document type is provided.
        """
        if doc_type == "class":
            result = self.classes.delete_many(filter_criteria)
        elif doc_type == "function":
            result = self.functions.delete_many(filter_criteria)
        else:
            raise ValueError("Invalid document type. Must be 'class' or 'function'.")
        return result.deleted_count

    def find_similar_functions(
        self,
        embedding_vector: List[float],
        parent_class_id: Optional[ObjectId] = None,
        function_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict]:
        """Finds similar functions using a vector search pipeline.

        Args:
            embedding_vector (List[float]): Query embedding vector.
            parent_class_id (Optional[ObjectId], optional): Filter by parent class. Defaults to None.
            function_type (Optional[str], optional): Filter by function type. Defaults to None.
            limit (int, optional): Number of results to return. Defaults to 10.

        Returns:
            List[dict]: List of function documents with similarity scores.
        """
        pipeline = [
            {
                "$vectorSearch": {
                    "queryVector": embedding_vector,
                    "path": "embedding_vector",
                    "numCandidates": limit * 10,
                    "limit": limit,
                    "index": "vector_search_function",
                }
            }
        ]
        match_conditions = {}
        if parent_class_id:
            match_conditions["parent_class_id"] = parent_class_id
        if function_type:
            match_conditions["type"] = function_type
        if match_conditions:
            pipeline.append({"$match": match_conditions})
        pipeline.extend([
            {
                "$lookup": {
                    "from": self.classes.name,
                    "localField": "parent_class_id",
                    "foreignField": "_id",
                    "as": "class",
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "name": 1,
                    "package": 1,
                    "signature": 1,
                    "type": 1,
                    "decorators": 1,
                    "docstring": 1,
                    "embedding_vector": 1,
                    "model": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "score": {"$meta": "vectorSearchScore"},
                    "class": {
                        "$cond": {
                            "if": {"$eq": ["$type", "method"]},
                            "then": {"$arrayElemAt": ["$class", 0]},
                            "else": None,
                        }
                    },
                }
            },
        ])
        return list(self.functions.aggregate(pipeline))

    def find_similar_classes(
        self,
        embedding_vector: List[float],
        limit: int = 10,
    ) -> List[dict]:
        """Finds similar classes using a vector search pipeline.

        Args:
            embedding_vector (List[float]): Query embedding vector.
            limit (int, optional): Number of results to return. Defaults to 10.

        Returns:
            List[dict]: List of class documents with similarity scores.
        """
        pipeline = [
            {
                "$vectorSearch": {
                    "queryVector": embedding_vector,
                    "path": "embedding_vector",
                    "numCandidates": limit * 10,
                    "limit": limit,
                    "index": "vector_search_class",
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "name": 1,
                    "package": 1,
                    "signature": 1,
                    "type": 1,
                    "decorators": 1,
                    "docstring": 1,
                    "embedding_vector": 1,
                    "model": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        return list(self.classes.aggregate(pipeline))

    def search_code(
        self,
        query_vector: List[float],
        limit: int = 10,
        search_type: str = "all",
        function_type: Optional[str] = None,
    ) -> Dict[str, List[dict]]:
        """Searches for similar classes and functions based on a query vector.

        Args:
            query_vector (List[float]): Query embedding vector.
            limit (int, optional): Number of results per type. Defaults to 10.
            search_type (str, optional): Type of search: "all", "classes", or "functions". Defaults to "all".
            function_type (Optional[str], optional): Filter functions by type. Defaults to None.

        Returns:
            Dict[str, List[dict]]: Dictionary containing search results for classes and/or functions.
        """
        results = {}
        if search_type in ["all", "classes"]:
            results["classes"] = self.find_similar_classes(query_vector, limit)
        if search_type in ["all", "functions"]:
            results["functions"] = self.find_similar_functions(
                query_vector, function_type=function_type, limit=limit
            )
        return results

    def close(self):
        """Closes the MongoDB client connection."""
        self.client.close()
