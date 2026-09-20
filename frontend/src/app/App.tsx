import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './Layout'
import { LoadingState } from '../components/business/BusinessPage'

const Dashboard = lazy(() => import('../pages/Dashboard').then(module => ({ default:module.Dashboard })))
const LibraryCenter = lazy(() => import('../pages/Library').then(module => ({ default:module.LibraryCenter })))
const PersonDetail = lazy(() => import('../pages/Library').then(module => ({ default:module.PersonDetail })))
const MediaCenter = lazy(() => import('../pages/Media').then(module => ({ default:module.MediaCenter })))
const MediaDetail = lazy(() => import('../pages/Media').then(module => ({ default:module.MediaDetail })))
const NewTask = lazy(() => import('../pages/NewTask').then(module => ({ default:module.NewTask })))
const Results = lazy(() => import('../pages/Results').then(module => ({ default:module.Results })))
const ResultDetail = lazy(() => import('../pages/Results').then(module => ({ default:module.ResultDetail })))
const Review = lazy(() => import('../pages/Review').then(module => ({ default:module.Review })))
const TaskDetail = lazy(() => import('../pages/TaskDetail').then(module => ({ default:module.TaskDetail })))
const Tasks = lazy(() => import('../pages/Tasks').then(module => ({ default:module.Tasks })))
const ValidationTools = lazy(() => import('../pages/ValidationTools').then(module => ({ default:module.ValidationTools })))
const Workbench = lazy(() => import('../pages/Workbench').then(module => ({ default:module.Workbench })))

export function App() {
  return <Suspense fallback={<div className="grid h-full min-h-64 place-items-center"><LoadingState/></div>}><Routes>
    <Route path="/tasks/:taskId/review" element={<Review/>}/>
    <Route element={<Layout/>}>
      <Route path="/overview" element={<Dashboard/>}/>
      <Route path="/workbench" element={<Workbench/>}/>
      <Route path="/tasks" element={<Tasks/>}/>
      <Route path="/tasks/new" element={<NewTask/>}/>
      <Route path="/tasks/:taskId" element={<TaskDetail/>}/>
      <Route path="/media" element={<MediaCenter/>}/>
      <Route path="/media/:mediaId" element={<MediaDetail/>}/>
      <Route path="/library/:section" element={<LibraryCenter/>}/>
      <Route path="/library/people/:itemId" element={<PersonDetail/>}/>
      <Route path="/results" element={<Results/>}/>
      <Route path="/results/:taskId" element={<ResultDetail/>}/>
      <Route path="/validation/tools" element={<ValidationTools/>}/>
      <Route index element={<Navigate to="/overview" replace/>}/>
      <Route path="*" element={<Navigate to="/overview" replace/>}/>
    </Route>
  </Routes></Suspense>
}
