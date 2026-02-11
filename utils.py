import os
import uuid

import psycopg2


def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="postgres",
        user="postgres",
        password="ZXC9988666ZXC",
    )

def get_collection_name_from_db(conversation_id:str):
    conn=get_db_connection()
    cur=conn.cursor()
    cur.execute("SELECT collection_name FROM conversations WHERE id=%s", (conversation_id,))
    result=cur.fetchone()
    cur.close()
    conn.close()

    if not result:
        raise ValueError(f"对话 {conversation_id} 不存在")
    return result[0]

def save_file_record_to_db(conversation_id:str,filename:str,file_path:str):
    conn=get_db_connection()
    cur=conn.cursor()

    file_id=f'file_{uuid.uuid4().hex}'
    file_type=os.path.splitext(filename)[1][1:]

    cur.execute("""
            INSERT INTO uploaded_files (id, conversation_id, filename, file_path, file_type)
            VALUES (%s, %s, %s, %s, %s)
        """, (file_id, conversation_id, filename, file_path, file_type))

    conn.commit()
    cur.close()
    conn.close()

def insert_conversation_to_db(conversation_id:str,title:str,collection_name:str):
    conn=get_db_connection()
    cur=conn.cursor()
    cur.execute("""
                INSERT INTO conversations (id, title, collection_name)
                VALUES (%s, %s, %s)
                """, (conversation_id, title, collection_name))
    conn.commit()
    cur.close()
    conn.close()

def get_all_conversations():
    conn=get_db_connection()
    cur=conn.cursor()
    cur.execute("""
                SELECT id, title,updated_at FROM conversations
                """)
    result=cur.fetchall()
    return result

def get_messages_from_conversation(conversation_id):
    conn=get_db_connection()
    cur=conn.cursor()
    cur.execute("""
                select messages.id, messages.role, messages.content, messages.sources,messages.created_at
                FROM messages
                WHERE conversation_id= %s
                ORDER BY created_at ASC
                """, (conversation_id,))
    result=cur.fetchall()
    return result


def insert_message_to_db(conversation_id:str,role,content,source):
    message_id = f'msg_{uuid.uuid4().hex}'
    conn=get_db_connection()
    cur=conn.cursor()
    cur.execute("""
    INSERT INTO messages (id,conversation_id, role, content, source)
    VALUES (%s, %s, %s, %s, %s)
    """, (message_id, conversation_id, role, content, source))

    conn.commit()
    cur.close()
    conn.close()

