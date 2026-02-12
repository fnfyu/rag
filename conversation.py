import uuid

from fastapi import APIRouter

from backend import Loader
from utils import get_collection_name_from_db, insert_conversation_to_db, get_all_conversations, \
    get_messages_from_conversation

router = APIRouter()

@router.post("/conversations/create")
async def create_conversation(title:str="新对话"):
    conversation_id = f'conv_{uuid.uuid4().hex}'
    collection_name = f'col_{uuid.uuid4().hex}'
    Loader.chroma_client.get_or_create_collection(collection_name)

    insert_conversation_to_db(conversation_id, title,collection_name)

    return {
        "conversation_id": conversation_id,
        "title": title,
        "collection_name": collection_name
        }

@router.get("/conversations/list")
async def list_conversations():
    conversations=get_all_conversations()
    return [{
        'id':id,
        'title':title,
        'updated_at':updated_at
        }
        for id,title,updated_at in conversations
    ]
# @router.post("/conversations/delete")
# async def delete_conversation(body:dict):

@router.get("/conversations/list/{conversation_id}")
async def load_conversation(conversation_id:str):
    conversation=get_messages_from_conversation(conversation_id)
    return [
        {
            "id": id,
            "role": role,
            "parts":[
                {
                    'type':'text',
                    'text':content
                },
                {
                    'type':'data-sources',
                    'data':sources
                }

            ],
            "sources": sources,
            "created_at": created_at
        }
        for id,role,content,sources,created_at in conversation
    ]