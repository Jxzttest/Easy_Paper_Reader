My first agnet project is mainly used for practicing, and I welcome criticism and guidance from all parties





Redis 数据库功能：对话上下文
es 数据库功能：
1、存储对话内容；  记录 用户输入 ai最终返回内容  
2、存储论文文本信息;  记录论文每一页 每个chunk的信息 包括 boxx content 也包括图片、公式 表格等
3、存储agent 的中间过程 记录 agent 任务信息、agent名称 、工具使用名称、中间结果、执行状态、调用时间 等内容

postgresql 数据库功能：1、存储论文元数据；2、存储用户数据；3、存储对话结构化历史