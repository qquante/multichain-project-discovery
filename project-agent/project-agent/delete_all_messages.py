"""
Script para deletar todas as mensagens de tópicos específicos em um grupo do Telegram.
Implementa rate limiting para evitar bloqueios da API.
"""

import asyncio
import time
from telegram import Bot
from telegram.error import TelegramError, RetryAfter, BadRequest

# Configuração
TELEGRAM_BOT_TOKEN = "[REMOVED_CREDENTIAL]"
TELEGRAM_GROUP_ID = -1003466463312

# IDs dos tópicos
TOPICS = {
    "STAGE_0": 10,
    "STAGE_1": 3,
    "MENTIONS": 637,
    "STAGE_2": 5,
    "STAGE_3": 7,
    "FINGERPRINTS": 12,
}

# Rate limiting config
REQUESTS_PER_SECOND = 25  # Um pouco mais agressivo
DELAY_BETWEEN_REQUESTS = 1 / REQUESTS_PER_SECOND


class RateLimiter:
    """Controla a taxa de requisições para a API do Telegram."""
    
    def __init__(self, requests_per_second: float):
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0
    
    async def wait(self):
        """Aguarda o tempo necessário antes da próxima requisição."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            wait_time = self.min_interval - time_since_last
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()


async def get_latest_message_id(bot: Bot, chat_id: int, topic_id: int = None) -> int:
    """
    Envia uma mensagem temporária para descobrir o ID mais recente e depois a deleta.
    """
    try:
        if topic_id:
            msg = await bot.send_message(
                chat_id=chat_id,
                text="🔍 Buscando último ID...",
                message_thread_id=topic_id
            )
        else:
            msg = await bot.send_message(
                chat_id=chat_id,
                text="🔍 Buscando último ID..."
            )
        
        latest_id = msg.message_id
        
        # Deleta a mensagem temporária
        try:
            await bot.delete_message(chat_id=chat_id, message_id=latest_id)
        except:
            pass
        
        return latest_id
    except Exception as e:
        print(f"  ⚠️ Não conseguiu obter último ID: {e}")
        return 10000  # Fallback


async def delete_message_safe(bot: Bot, chat_id: int, message_id: int, rate_limiter: RateLimiter) -> bool:
    """
    Tenta deletar uma mensagem com tratamento de erros e rate limiting.
    Retorna True se deletou com sucesso, False caso contrário.
    """
    await rate_limiter.wait()
    
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except RetryAfter as e:
        print(f"  ⏳ Rate limit! Aguardando {e.retry_after}s...")
        await asyncio.sleep(e.retry_after + 1)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except Exception:
            return False
    except BadRequest as e:
        error_msg = str(e).lower()
        if "message to delete not found" in error_msg:
            return False
        if "message can't be deleted" in error_msg:
            return False
        return False
    except TelegramError:
        return False


async def delete_topic_messages(bot: Bot, chat_id: int, topic_id: int, topic_name: str, rate_limiter: RateLimiter):
    """
    Deleta todas as mensagens de um tópico específico.
    COMEÇA DO ÚLTIMO ID e vai para trás (muito mais rápido!)
    """
    print(f"\n{'='*60}")
    print(f"🗑️  Deletando mensagens do tópico: {topic_name} (ID: {topic_id})")
    print(f"{'='*60}")
    
    # Descobre o último ID de mensagem
    print(f"  🔍 Buscando último ID de mensagem...")
    latest_id = await get_latest_message_id(bot, chat_id, topic_id)
    print(f"  📍 Último ID encontrado: {latest_id}")
    
    deleted_count = 0
    not_found_streak = 0
    max_not_found_streak = 200  # Para depois de 200 não encontradas seguidas
    
    # Começa do último ID e vai para trás
    message_id = latest_id
    
    print(f"  ⬇️ Deletando de {latest_id} até 1...")
    
    while message_id > 0 and not_found_streak < max_not_found_streak:
        success = await delete_message_safe(bot, chat_id, message_id, rate_limiter)
        
        if success:
            deleted_count += 1
            not_found_streak = 0
            if deleted_count % 10 == 0:
                print(f"  ✅ {deleted_count} deletadas (atual: {message_id})")
        else:
            not_found_streak += 1
        
        message_id -= 1
    
    print(f"\n  ✨ Tópico {topic_name}: {deleted_count} mensagens deletadas")
    return deleted_count


async def delete_all_messages_in_group(bot: Bot, chat_id: int, rate_limiter: RateLimiter):
    """
    Deleta mensagens gerais do grupo (começando do último ID).
    """
    print(f"\n{'='*60}")
    print(f"🗑️  Deletando mensagens gerais do grupo")
    print(f"{'='*60}")
    
    # Descobre o último ID
    print(f"  🔍 Buscando último ID de mensagem...")
    latest_id = await get_latest_message_id(bot, chat_id)
    print(f"  📍 Último ID encontrado: {latest_id}")
    
    deleted_count = 0
    not_found_streak = 0
    max_not_found_streak = 300
    
    message_id = latest_id
    
    print(f"  ⬇️ Deletando de {latest_id} até 1...")
    
    while message_id > 0 and not_found_streak < max_not_found_streak:
        success = await delete_message_safe(bot, chat_id, message_id, rate_limiter)
        
        if success:
            deleted_count += 1
            not_found_streak = 0
            if deleted_count % 10 == 0:
                print(f"  ✅ {deleted_count} deletadas (atual: {message_id})")
        else:
            not_found_streak += 1
        
        message_id -= 1
    
    print(f"\n  ✨ Mensagens gerais: {deleted_count} deletadas")
    return deleted_count


async def main():
    print("🤖 Iniciando bot de limpeza do Telegram...")
    print(f"📍 Grupo ID: {TELEGRAM_GROUP_ID}")
    print(f"📋 Tópicos a limpar: {list(TOPICS.keys())}")
    print(f"⏱️  Rate limit: {REQUESTS_PER_SECOND} requests/segundo")
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    rate_limiter = RateLimiter(REQUESTS_PER_SECOND)
    
    # Verifica se o bot está funcionando
    try:
        bot_info = await bot.get_me()
        print(f"\n✅ Bot conectado: @{bot_info.username}")
    except Exception as e:
        print(f"\n❌ Erro ao conectar ao bot: {e}")
        return
    
    # Verifica informações do chat
    try:
        chat = await bot.get_chat(chat_id=TELEGRAM_GROUP_ID)
        print(f"✅ Grupo encontrado: {chat.title}")
    except Exception as e:
        print(f"\n❌ Erro ao acessar o grupo: {e}")
        return
    
    total_deleted = 0
    
    # Primeiro deleta mensagens gerais (pega o ID mais recente global)
    try:
        deleted = await delete_all_messages_in_group(bot, TELEGRAM_GROUP_ID, rate_limiter)
        total_deleted += deleted
    except Exception as e:
        print(f"  ❌ Erro nas mensagens gerais: {e}")
    
    # Depois deleta mensagens de cada tópico
    for topic_name, topic_id in TOPICS.items():
        try:
            deleted = await delete_topic_messages(bot, TELEGRAM_GROUP_ID, topic_id, topic_name, rate_limiter)
            total_deleted += deleted
        except Exception as e:
            print(f"  ❌ Erro no tópico {topic_name}: {e}")
    
    print(f"\n{'='*60}")
    print(f"🎉 LIMPEZA CONCLUÍDA!")
    print(f"📊 Total de mensagens deletadas: {total_deleted}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
