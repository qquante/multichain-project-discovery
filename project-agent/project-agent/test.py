#!/usr/bin/env python3
"""
MongoDB Explorer - Analisa estrutura completa do banco para RL Training
"""

from pymongo import MongoClient
from collections import Counter
import json
from datetime import datetime

# Conectar no MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["eltrigger"]

print("=" * 80)
print("🔍 MONGODB EXPLORER - ELTRIGGER DATABASE")
print("=" * 80)

# 1. Listar todas as collections com contagem
print("\n📊 COLLECTIONS E QUANTIDADE DE DOCUMENTOS:")
print("-" * 50)

collections_info = []
for name in db.list_collection_names():
    count = db[name].count_documents({})
    size = db.command("collstats", name).get("size", 0) / (1024 * 1024)  # MB
    collections_info.append({"name": name, "count": count, "size_mb": round(size, 2)})
    print(f"  📁 {name}: {count:,} docs ({size:.2f} MB)")

collections_info.sort(key=lambda x: x["count"], reverse=True)

# 2. Analisar schema de cada collection
print("\n" + "=" * 80)
print("📋 ESTRUTURA DE CADA COLLECTION:")
print("=" * 80)

def get_schema(doc, prefix=""):
    """Extrai schema de um documento"""
    schema = {}
    if isinstance(doc, dict):
        for key, value in doc.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                schema[full_key] = "object"
                schema.update(get_schema(value, full_key))
            elif isinstance(value, list):
                schema[full_key] = f"array[{len(value)}]"
                if value and isinstance(value[0], dict):
                    schema.update(get_schema(value[0], f"{full_key}[]"))
            else:
                schema[full_key] = type(value).__name__
    return schema

def analyze_collection(collection_name, sample_size=100):
    """Analisa uma collection e retorna estatísticas"""
    collection = db[collection_name]
    
    # Pegar amostra
    docs = list(collection.find().limit(sample_size))
    if not docs:
        return None
    
    # Agregar schemas
    all_keys = Counter()
    for doc in docs:
        schema = get_schema(doc)
        for key, val_type in schema.items():
            all_keys[f"{key} ({val_type})"] += 1
    
    return {
        "sample_size": len(docs),
        "fields": dict(all_keys.most_common(50)),  # Top 50 campos
        "example": docs[0] if docs else None
    }

# Analisar cada collection
for coll_info in collections_info:
    name = coll_info["name"]
    print(f"\n{'─' * 80}")
    print(f"📁 COLLECTION: {name}")
    print(f"   Documentos: {coll_info['count']:,} | Tamanho: {coll_info['size_mb']} MB")
    print(f"{'─' * 80}")
    
    analysis = analyze_collection(name)
    if analysis:
        print(f"\n   📌 CAMPOS ENCONTRADOS (amostra de {analysis['sample_size']} docs):")
        for field, count in list(analysis["fields"].items())[:30]:
            print(f"      • {field}: {count}/{analysis['sample_size']}")
        
        # Mostrar exemplo (resumido)
        print(f"\n   📝 EXEMPLO (1 documento):")
        example = analysis["example"]
        if example:
            # Converter ObjectId e datetime para string
            def serialize(obj):
                if hasattr(obj, '__str__') and not isinstance(obj, (str, int, float, bool, list, dict, type(None))):
                    return str(obj)
                return obj
            
            example_str = json.dumps(example, default=serialize, indent=6, ensure_ascii=False)
            # Limitar tamanho
            if len(example_str) > 2000:
                example_str = example_str[:2000] + "\n      ... (truncado)"
            print(example_str)

# 3. Identificar collections importantes para RL
print("\n" + "=" * 80)
print("🎯 ANÁLISE PARA RL TRAINING:")
print("=" * 80)

# Procurar collections com dados de projetos
rl_candidates = []
keywords = ["project", "tweet", "decision", "outcome", "hunter", "alpha", "token", "analysis"]

for coll_info in collections_info:
    name = coll_info["name"].lower()
    if any(kw in name for kw in keywords) or coll_info["count"] > 100:
        rl_candidates.append(coll_info)
        print(f"\n  ✅ {coll_info['name']}: {coll_info['count']:,} docs")
        
        # Ver campos importantes
        sample = db[coll_info["name"]].find_one()
        if sample:
            important_fields = [k for k in sample.keys() if any(
                x in k.lower() for x in ["status", "score", "decision", "outcome", "approved", "rejected", "scam", "spam", "confidence"]
            )]
            if important_fields:
                print(f"     Campos importantes: {important_fields}")

# 4. Estatísticas finais
print("\n" + "=" * 80)
print("📈 RESUMO FINAL:")
print("=" * 80)
total_docs = sum(c["count"] for c in collections_info)
total_size = sum(c["size_mb"] for c in collections_info)
print(f"  Total de Collections: {len(collections_info)}")
print(f"  Total de Documentos: {total_docs:,}")
print(f"  Tamanho Total: {total_size:.2f} MB")

print("\n✅ Exploração completa! Use esses dados para montar o pipeline de RL.")
