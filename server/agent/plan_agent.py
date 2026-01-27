from agents.base_agent import BaseAgent
from skills.formatter import format_itinerary

class PlanAgent(BaseAgent):
    """行程规划智能体 - 负责生成详细行程"""
    
    def __init__(self):
        super().__init__()
        self.name = "行程规划专家"
        self.expertise = ["行程规划", "时间管理", "景点推荐"]
    
    def execute(self, task, params, context=None):
        """执行任务的核心方法"""
        print(f"🤖 {self.name} 开始工作: {task}")
        
        try:
            # 从参数中获取信息
            destination = params.get('destination', '未知地点')
            days = params.get('days', 3)
            theme = params.get('theme', '文化')
            destination_info = params.get('destination_info', {})
            
            # 调用技能层
            itinerary = self._generate_itinerary(destination, days, theme, destination_info)
            
            # 记录执行日志
            self.log_execution({
                'agent': self.name,
                'task': task,
                'params': params,
                'status': 'success',
                'result_summary': f'生成了{days}天{theme}主题行程'
            })
            
            return {
                'status': 'success',
                'plan': {
                    'destination': destination,
                    'days': days,
                    'theme': theme,
                    'itinerary': itinerary
                },
                'log': self.get_execution_log()
            }
            
        except Exception as e:
            self.log_execution({
                'agent': self.name,
                'task': task,
                'params': params,
                'status': 'error',
                'error': str(e)
            })
            return {
                'status': 'error',
                'error': str(e),
                'log': self.get_execution_log()
            }
    
    def _generate_itinerary(self, destination, days, theme, destination_info):
        """生成详细行程（模拟）"""
        # 这里可以集成真实的AI模型或规则引擎
        # 目前使用模拟数据
        
        itinerary = []
        attractions = destination_info.get('attractions', [f'{destination}著名景点'])
        
        for day in range(1, days + 1):
            if day == 1:
                activities = [
                    "上午：抵达目的地，入住酒店",
                    "下午：参观" + (attractions[0] if attractions else "当地地标"),
                    "晚上：品尝当地特色美食"
                ]
            elif day == days:
                activities = [
                    "上午：自由活动，购买纪念品",
                    f"下午：参观{attractions[-1] if len(attractions) > 1 else '当地博物馆'}",
                    "晚上：整理行李，准备返程"
                ]
            else:
                activities = [
                    f"上午：探索{theme}相关景点",
                    "下午：参加当地体验活动",
                    "晚上：休闲漫步，体验当地夜生活"
                ]
            
            itinerary.append({
                'day': day,
                'activities': activities
            })
        
        # 调用格式化技能
        formatted_itinerary = format_itinerary(itinerary)
        return formatted_itinerary