import { HomeIcon, BookOpenIcon, MessageSquareIcon, NetworkIcon } from "lucide-react";
import Dashboard from "./pages/Dashboard.jsx";
import Reader from "./pages/Reader.jsx";
import KnowledgeGraph from "./pages/KnowledgeGraph.jsx";

/**
* Central place for defining the navigation items. Used for navigation components and routing.
*/
export const navItems = [
{
    title: "论文库",
    to: "/",
    icon: <BookOpenIcon className="h-4 w-4" />,
    page: <Dashboard />,
},
{
    title: "知识图谱",
    to: "/knowledge-graph",
    icon: <NetworkIcon className="h-4 w-4" />,
    page: <KnowledgeGraph />,
},
{
    title: "阅读器",
    to: "/reader/:paperId",
    icon: <MessageSquareIcon className="h-4 w-4" />,
    page: <Reader />,
},
];
