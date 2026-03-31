# pip install chromadb sentence-transformers
import uuid
from datetime import time

import chromadb

class RAGMemory:
    def __init__(self):
        # 初始化本地数据库，数据会保存在 ./agent_memory 文件夹下
        self.client = chromadb.PersistentClient(path="./agent_memory")
        # 创建一个名为 "sts_knowledge" 的集合
        self.collection = self.client.get_or_create_collection(name="sts_knowledge")

    def auto_save_experience(self, encounter_name, lesson_text):
        """
        自动写入经验的核心方法
        :param encounter_name: 遭遇的怪物或事件名（用作元数据，方便以后过滤）
        :param lesson_text: 大模型总结出来的纯文字经验教训
        """
        # 生成一个随机且唯一的 ID
        doc_id = f"exp_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        # 存入 ChromaDB
        self.collection.add(
            documents=[lesson_text],  # 存入纯文本的经验
            metadatas=[{"encounter": encounter_name, "type": "auto_reflection"}],  # 打上标签
            ids=[doc_id]
        )
        print(f"💾 [记忆库] 已自动写入一条关于【{encounter_name}】的新经验！")

    def search_memory(self, query_text, top_k=2):
        """检索记忆"""
        results = self.collection.query(
            query_texts=[query_text],
            n_results=top_k
        )
        if results['documents'] and results['documents'][0]:
            return "\n".join(results['documents'][0])
        return ""