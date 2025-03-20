"""
models.py
=========

This module defines the Pydantic models used for code component indexing.
It includes custom validation for MongoDB ObjectIds as well as the following models:
  - ObjectIdPydanticAnnotation: A custom annotation for validating and serializing MongoDB ObjectIds.
  - BaseResponseModel: Base model with CRUD operations for MongoDB.
  - FunctionDocumentModel: Represents a function or method document with associated metadata.
  - ClassDocumentModel: Represents a class document with associated metadata.
"""


from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Any, Annotated, Self
from bson import ObjectId
from pymongo.collection import Collection
from pydantic import BaseModel, Field
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema


class ObjectIdPydanticAnnotation:
    @classmethod
    def validate_object_id(cls, v: Any, handler) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        s = handler(v)
        if ObjectId.is_valid(s):
            return ObjectId(s)
        else:
            raise ValueError("Invalid ObjectId")

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type, _handler
    ) -> core_schema.CoreSchema:
        assert source_type is ObjectId
        return core_schema.no_info_wrap_validator_function(
            cls.validate_object_id,
            core_schema.str_schema(),
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema, handler) -> JsonSchemaValue:
        return handler(core_schema.str_schema())


class BaseResponseModel(BaseModel):
    """Base model providing MongoDB CRUD operations for code components."""
    __doc_name__: str = ""  # Expected format: "<database>.<collection>"

    id: Annotated[ObjectId, ObjectIdPydanticAnnotation] = Field(
        default_factory=ObjectId, alias="_id"
    )

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True

    @classmethod
    def collection(cls, conn) -> Optional[Collection]:
        try:
            db, col = cls.__doc_name__.split(".")
            return conn.get_database(db).get_collection(col)
        except ValueError:
            return None

    @classmethod
    def find_one(cls, conn, query: dict) -> Optional[Self]:
        col = cls.collection(conn)
        if col:
            cursor = col.find_one(query)
            if cursor:
                return cls.model_validate(cursor)
        return None

    @classmethod
    def find(cls, conn, query: dict, sort: dict = None) -> List[Self]:
        col = cls.collection(conn)
        results = []
        if col:
            cursor = col.find(query)
            if sort:
                cursor = cursor.sort(sort)
            results = [cls.model_validate(item) for item in cursor]
        return results

    def save(self, conn) -> Self:
        col = self.collection(conn)
        res = col.insert_one(self.model_dump())
        if res.inserted_id:
            self._id = res.inserted_id
        return self

    @classmethod
    def save_all(cls, conn, items: list[Self]) -> List[ObjectId]:
        col = cls.collection(conn)
        res = col.insert_many([item.model_dump() for item in items])
        return res.inserted_ids

    @classmethod
    def delete(cls, conn, query: dict) -> None:
        col = cls.collection(conn)
        col.delete_one(query)

    @classmethod
    def delete_all(cls, conn, query: dict) -> int:
        col = cls.collection(conn)
        result = col.delete_many(query)
        return result.deleted_count

    @classmethod
    def update(cls, conn, query: dict, update_data: dict) -> Optional[Self]:
        col = cls.collection(conn)
        result = col.update_one(query, {"$set": update_data})
        if result.modified_count > 0:
            return cls.find_one(conn, query)
        return None

    @classmethod
    def update_all(cls, conn, query: dict, update_data: dict) -> int:
        col = cls.collection(conn)
        result = col.update_many(query, {"$set": update_data})
        return result.modified_count


class FunctionDocumentModel(BaseResponseModel):
    """
    Pydantic model for function or method document.
    
    Attributes:
        name (str): Name of the function.
        package (str): Package where the function is defined.
        parent_class_id (Optional[ObjectId]): Reference to parent class ObjectId if applicable.
        signature (str): Function signature.
        type (str): Type of function, e.g., "function", "async_function", or "method".
        decorators (List[str]): List of decorators applied to the function.
        embedding_vector (List[float]): Embedding vector for semantic search.
        docstring (str): Documentation string.
        model (str): Model identifier for the embedding.
        created_at (datetime): Timestamp when document was created.
        updated_at (datetime): Timestamp when document was last updated.
    """
    name: str
    package: str
    parent_class_id: Optional[ObjectId] = None
    signature: str
    type: str  # "function", "async_function", or "method"
    decorators: List[str]
    embedding_vector: List[float]
    docstring: str
    model: str
    created_at: datetime
    updated_at: datetime


class ClassDocumentModel(BaseResponseModel):
    """
    Pydantic model for class document.
    
    Attributes:
        name (str): Name of the class.
        package (str): Package where the class is defined.
        signature (str): Class signature.
        type (str): Document type; should be "class".
        decorators (List[str]): List of decorators applied to the class.
        embedding_vector (List[float]): Embedding vector for semantic search.
        member_variables (List[str]): List of member variables.
        function_ids (List[ObjectId]): List of function ObjectIds belonging to the class.
        docstring (str): Documentation string.
        model (str): Model identifier for the embedding.
        created_at (datetime): Timestamp when document was created.
        updated_at (datetime): Timestamp when document was last updated.
    """
    name: str
    package: str
    signature: str
    type: str  # should be "class"
    decorators: List[str]
    embedding_vector: List[float]
    member_variables: List[str]
    function_ids: List[ObjectId] = []
    docstring: str
    model: str
    created_at: datetime
    updated_at: datetime
