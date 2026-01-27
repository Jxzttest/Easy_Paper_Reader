class ContextManager:
    """管理多轮对话的上下文（状态机模式）"""
    
    def __init__(self):
        self.sessions = {}
    
    def update_context(self, session_id, user_input):
        """更新对话上下文，提取关键信息"""
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'conversation_history': [],
                'task_memory': {},
                'current_intent': None,
                'entities': {},
                'current_state': 'idle'  # idle, clarifying, executing, completed
            }
        
        context = self.sessions[session_id]
        
        # 将用户输入加入历史
        context['conversation_history'].append({
            'role': 'user',
            'content': user_input
        })
        
        # 意图识别（简化版）
        context['current_intent'] = self._detect_intent(user_input)
        
        # 实体提取
        entities = self._extract_entities(user_input)
        context['entities'].update(entities)
        
        # 更新任务内存
        if 'task' not in context['task_memory']:
            context['task_memory'] = {
                'task': context['current_intent'],
                'requirements': entities,
                'steps_completed': [],
                'results': {}
            }
        
        context['current_state'] = 'executing'
        return context
    
    def _detect_intent(self, text):
        """简单的意图识别"""
        text_lower = text.lower()
        if any(word in text_lower for word in ['旅行', '旅游', '行程', '出去玩']):
            return 'travel_planning'
        elif any(word in text_lower for word in ['预算', '花费', '多少钱', '费用']):
            return 'budget_analysis'
        elif any(word in text_lower for word in ['酒店', '住宿', '住哪里']):
            return 'accommodation_search'
        else:
            return 'general_inquiry'
    
    def _extract_entities(self, text):
        """提取关键实体信息（简化版）"""
        entities = {}
        # 提取天数
        import re
        day_match = re.search(r'(\d+)\s*天', text)
        if day_match:
            entities['days'] = int(day_match.group(1))
        
        # 提取预算
        budget_match = re.search(r'(\d+)\s*元', text)
        if budget_match:
            entities['budget'] = int(budget_match.group(1))
        
        # 提取地点
        locations = ['北京', '上海', '杭州', '成都', '广州', '深圳']
        for loc in locations:
            if loc in text:
                entities['destination'] = loc
                break
        
        # 提取主题
        themes = ['美食', '文化', '自然', '冒险', '家庭']
        for theme in themes:
            if theme in text:
                entities['theme'] = theme
                break
        
        return entities
    
    def needs_clarification(self, context):
        """检查是否需要澄清意图（ICPO思想）"""
        intent = context['current_intent']
        entities = context['entities']
        
        # 如果是旅行规划但缺少关键信息
        if intent == 'travel_planning':
            if 'destination' not in entities:
                return True
            if 'days' not in entities and 'budget' not in entities:
                return True
        
        return False
    
    def request_clarification(self, context):
        """请求用户澄清"""
        intent = context['current_intent']
        entities = context['entities']
        
        if intent == 'travel_planning':
            if 'destination' not in entities:
                return "请问您想去哪个城市旅行？"
            if 'days' not in entities:
                return f"您计划去{entities.get('destination')}玩几天呢？"
            if 'budget' not in entities:
                return f"您的大概预算是多少元？"
        
        return "请提供更多细节信息，以便我更好地帮助您。"
    
    def update_task_memory(self, session_id, result):
        """更新任务内存"""
        if session_id in self.sessions:
            if 'steps_completed' in result:
                self.sessions[session_id]['task_memory']['steps_completed'].extend(
                    result['steps_completed']
                )
            if 'results' in result:
                self.sessions[session_id]['task_memory']['results'].update(
                    result['results']
                )
    
    def get_context(self, session_id):
        """获取指定会话的上下文"""
        return self.sessions.get(session_id, {})