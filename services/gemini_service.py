import google.generativeai as genai
from telegram import Message
from config import config
import json
import random
import re
from PIL import Image
import io

class GeminiService:
    def __init__(self):
        if config.GEMINI_API_KEY:
            genai.configure(api_key=config.GEMINI_API_KEY)
            self.filter_model = genai.GenerativeModel('gemini-2.5-flash')
            self.verification_model = genai.GenerativeModel('gemini-2.5-flash-lite')
        else:
            self.filter_model = None
            self.verification_model = None
    
    async def analyze_message(self, message: Message, image_bytes: bytes = None) -> dict:
        if not self.filter_model or not config.ENABLE_AI_FILTER:
            return {"is_spam": False, "reason": "AI filter disabled"}

        content = []
        prompt_parts = [
            "你是一个内容审查员。你的任务是分析提供给你的文本和/或图片内容，并判断其是否包含垃圾信息、恶意软件、钓鱼链接、不当言论、辱骂、攻击性词语或任何违反安全政策的内容。",
            "请严格按照要求，仅以JSON格式返回你的分析结果，不要包含任何额外的解释或标记。",
            "**输出格式**: 你必须且只能以严格的JSON格式返回你的分析结果，不得包含任何解释性文字或代码块标记。",
            "**JSON结构**:\n```json\n{\n  \"is_spam\": boolean,\n  \"reason\": \"string\"\n}\n```\n*   `is_spam`: 如果内容违反**任何一条**安全策略，则为 `true`；如果内容完全安全，则为 `false`。\n*   `reason`: 用一句话精准概括判断依据。如果违规，请明确指出违规的类型。如果安全，此字段固定为 `\"内容未发现违规。\"`",
            "\n--- 以下是需要分析的内容 ---",
        ]

        if message.text:
            content.append(message.text)
        
        if image_bytes:
            try:
                image = Image.open(io.BytesIO(image_bytes))
                content.append(image)
            except Exception as e:
                print(f"Error processing image for Gemini: {e}")
                pass

        if not content:
            return {"is_spam": False, "reason": "No content to analyze"}

        content.append("\n".join(prompt_parts))

        print("--- Sending request to Gemini API ---")
        print(f"Content: {content}")

        try:
            response = await self.filter_model.generate_content_async(content)
            
            print("--- Received response from Gemini API ---")

            if not response.candidates:
                print("Gemini analysis was blocked.")
                if hasattr(response, 'prompt_feedback'):
                    print(f"Prompt feedback: {response.prompt_feedback}")
                return {"is_spam": True, "reason": "内容审查失败，可能包含不当内容。"}

            print(f"Raw response: {response.text}")

            if not response.text:
                raise ValueError("Gemini API returned an empty response.")
            
            clean_text = re.sub(r'```json\s*|\s*```', '', response.text).strip()
            result = json.loads(clean_text)
            
            print(f"Parsed result: {result}")
            return result
        except Exception as e:
            print(f"Gemini analysis failed: {e}")
            if 'response' in locals():
                try:
                    if response.candidates:
                        print(f"Original Gemini response: {response.text}")
                except ValueError:
                    print("Could not retrieve response.text.")
            return {"is_spam": False, "reason": "Analysis failed"}
    
    async def generate_unblock_question(self) -> dict:
        if not self.verification_model:
            return {
                "question": "中国的首都是哪里？",
                "answer": "北京"
            }
        
        prompt = """
        生成一个简单的常识问题用于解封验证。
        请以JSON格式回复: {{"question": "问题", "answer": "答案"}}
        """
        try:
            response = await self.verification_model.generate_content_async(prompt)
            return json.loads(response.text)
        except Exception as e:
            print(f"生成问题失败: {e}")
            return {
                "question": "中国的首都是哪里？",
                "answer": "北京"
            }

    async def generate_verification_challenge(self) -> dict:
        if not self.verification_model:
            return {
                "question": "1 + 1 = ?",
                "correct_answer": "2",
                "options": ["1", "2", "3", "4"]
            }

        prompt = """
        请生成一个用于人机验证的常识性问题。
        要求：
        1. 问题应该简单，大部分人都能回答。
        2. 提供一个正确答案和三个看起来合理但错误的干扰项。
        3. 所有内容必须为简体中文。
        4. 以JSON格式返回，包含以下键： "question", "correct_answer", "incorrect_answers" (一个包含三个字符串的列表)。
        
        示例:
        {
          "question": "太阳从哪个方向升起？",
          "correct_answer": "东方",
          "incorrect_answers": ["西方", "南方", "北方"]
        }
        """
        try:
            response = await self.verification_model.generate_content_async(prompt)
            
            if not response.text:
                raise ValueError("Gemini API返回空响应")

            
            clean_text = re.sub(r'```json\s*|\s*```', '', response.text).strip()
            data = json.loads(clean_text)
            
            
            correct_answer = data['correct_answer']
            options = data['incorrect_answers'] + [correct_answer]
            random.shuffle(options)
            
            return {
                "question": data['question'],
                "correct_answer": correct_answer,
                "options": options
            }
        except Exception as e:
            print(f"生成验证问题失败: {e}")
            
            if 'response' in locals() and hasattr(response, 'text'):
                print(f"Gemini原始响应: {response.text}")
            
            return {
                "question": "1 + 1 = ?",
                "correct_answer": "2",
                "options": ["1", "2", "3", "4"]
            }

gemini_service = GeminiService()