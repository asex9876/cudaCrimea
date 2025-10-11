import { createBrowserRouter } from "react-router-dom";

import RootLayout from "./layouts/RootLayout";
import DashboardPage from "./pages/DashboardPage";
import UgcPage from "./pages/UgcPage";
import SchedulerPage from "./pages/SchedulerPage";
import SettingsPage from "./pages/SettingsPage";
import NotFoundPage from "./pages/NotFoundPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "ugc", element: <UgcPage /> },
      { path: "scheduler", element: <SchedulerPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

export default router;
