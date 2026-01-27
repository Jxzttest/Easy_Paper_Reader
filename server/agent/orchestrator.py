from agents.info_agent import InfoAgent
from agents.plan_agent import PlanAgent
from agents.budget_agent import BudgetAgent

class Orchestrator:
    """中心化编排器 - 系统的指挥中枢"""
    
    def __init__(self):
        # 初始化智能体池
        self.agents = {
            'info': InfoAgent(),
            'plan': PlanAgent(),
            'budget': BudgetAgent()
        }
        print("✅ 编排器初始化完成，智能体池已加载")
    
    def execute_task(self, context):
        """执行任务的主要方法"""
        intent = context.get('current_intent')
        entities = context.get('entities', {})
        task_memory = context.get('task_memory', {})
        
        print(f"\n🎯 开始执行任务: {intent}")
        print(f"📋 实体信息: {entities}")
        
        agent_logs = []
        results = {}
        steps_completed = []
        
        # 根据意图规划任务流
        if intent == 'travel_planning':
            # 任务1: 信息查询
            print("\n1️⃣ 调度信息查询智能体...")
            info_result = self.agents['info'].execute(
                task="查询目的地信息",
                params={
                    'destination': entities.get('destination'),
                    'theme': entities.get('theme', '文化')
                },
                context=context
            )
            agent_logs.append(info_result.get('log', {}))
            results['destination_info'] = info_result.get('data', {})
            steps_completed.append('info_query')
            
            # 任务2: 行程规划
            print("\n2️⃣ 调度行程规划智能体...")
            plan_result = self.agents['plan'].execute(
                task="生成详细行程",
                params={
                    'destination': entities.get('destination'),
                    'days': entities.get('days', 3),
                    'theme': entities.get('theme', '文化'),
                    'destination_info': results['destination_info']
                },
                context=context
            )
            agent_logs.append(plan_result.get('log', {}))
            results['travel_plan'] = plan_result.get('plan', {})
            steps_completed.append('plan_generation')
            
            # 任务3: 预算分析
            print("\n3️⃣ 调度预算分析智能体...")
            budget_result = self.agents['budget'].execute(
                task="分析旅行预算",
                params={
                    'destination': entities.get('destination'),
                    'days': entities.get('days', 3),
                    'budget': entities.get('budget'),
                    'travel_plan': results['travel_plan']
                },
                context=context
            )
            agent_logs.append(budget_result.get('log', {}))
            results['budget_analysis'] = budget_result.get('analysis', {})
            steps_completed.append('budget_analysis')
            
            # 生成最终输出
            final_output = self._generate_final_output(results, entities)
            
        else:
            # 其他意图处理
            final_output = "我目前主要专注于旅行规划任务。"
        
        return {
            'final_output': final_output,
            'agent_logs': agent_logs,
            'results': results,
            'steps_completed': steps_completed
        }
    
    def _generate_final_output(self, results, entities):
        """生成最终回复"""
        destination = entities.get('destination', '目的地')
        days = entities.get('days', 3)
        
        output = f"""🌍 {destination} {days}天旅行规划完成！

📌 目的地特色：{results.get('destination_info', {}).get('highlights', '')}

🗓️ 行程安排：
{results.get('travel_plan', {}).get('itinerary', '暂无行程')}

💰 预算分析：
{results.get('budget_analysis', {}).get('summary', '暂无预算分析')}

📝 温馨提示：
1. 以上信息仅供参考，实际价格可能有所变动
2. 建议提前预订酒店和门票
3. 根据天气情况调整行程安排

祝您旅途愉快！✈️"""
        
        return output