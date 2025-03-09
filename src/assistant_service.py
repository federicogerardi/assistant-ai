import logging
import json
from typing import List, Dict, Any
from openai import OpenAI
import numpy as np

logger = logging.getLogger(__name__)

class AssistantService:
    def __init__(self, document_service):
        """Initialize assistant service with tools and OpenAI client."""
        self.client = OpenAI()
        self.document_service = document_service
        self.tools = self._register_tools()
        
        logger.info("AssistantService initialized with %d tools", len(self.tools))

    def _register_tools(self) -> List[Dict[str, Any]]:
        """Register all available tools for the assistant."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_documents",
                    "description": "Search through the available documents for relevant information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return",
                                "default": 3
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    def _convert_to_json_serializable(self, obj: Any) -> Any:
        """Convert objects to JSON serializable format."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.int64, np.int32, np.float64, np.float32)):
            return obj.item()
        if isinstance(obj, dict):
            return {k: self._convert_to_json_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._convert_to_json_serializable(i) for i in obj]
        return obj

    def execute_function(self, name: str, args: Dict[str, Any]) -> Any:
        """Execute a function by name with given arguments."""
        logger.info(f"🔧 Function called: {name}")
        logger.info(f"📝 Arguments: {json.dumps(args, indent=2)}")
        
        if name == "search_documents":
            results = self.document_service.search_documents(
                args["query"], 
                args.get("num_results", 3)
            )
            logger.info(f"📊 Found {len(results)} results")
            # Convertiamo i risultati in formato JSON-serializable
            json_safe_results = self._convert_to_json_serializable(results)
            return {"results": json_safe_results}
        
        else:
            logger.warning(f"❌ Unknown function: {name}")
            return None

    def get_assistant_response(self, messages: List[Dict[str, str]], context: str = "") -> str:
        """Get response from assistant with function calling capabilities."""
        try:
            system_prompt = f"""You are a helpful assistant that answers questions based on the provided context.
            Use the available tools to search for information when needed.
            If you're unsure or can't find relevant information, say so.
            
            Context:
            {context}
            """
            
            messages_with_context = [
                {"role": "system", "content": system_prompt},
                *messages
            ]
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=messages_with_context,
                tools=self.tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                messages_with_context.append(response_message)
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    function_response = self.execute_function(function_name, function_args)
                    # Convertiamo la risposta in formato JSON-serializable
                    json_safe_response = self._convert_to_json_serializable(function_response)
                    
                    messages_with_context.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(json_safe_response)
                    })
                
                final_response = self.client.chat.completions.create(
                    model="gpt-4",
                    messages=messages_with_context
                )
                
                return final_response.choices[0].message.content
            
            return response_message.content
            
        except Exception as e:
            logger.error(f"Error getting assistant response: {str(e)}", exc_info=True)
            return "Mi dispiace, si è verificato un errore nel generare la risposta." 