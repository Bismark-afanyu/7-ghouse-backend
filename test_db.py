import asyncio
from app.db.firebase import db

def main():
    docs = db.collection("generations").order_by("created_at", direction="DESCENDING").limit(1).get()
    if not docs:
        print("No generations")
        return
    gen = docs[0].to_dict()
    print("Generation:", docs[0].id)
    print("External status:", gen.get("video_external_status"))
    print("External project_id:", gen.get("video_external_project_id"))
    print("External error:", gen.get("video_external_error"))

main()
