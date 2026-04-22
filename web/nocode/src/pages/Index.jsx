import { Navigate } from 'react-router-dom';

// 首页重定向到论文库
const Index = () => {
  return <Navigate to="/" replace />;
};

export default Index;
