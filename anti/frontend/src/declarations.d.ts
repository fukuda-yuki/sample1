declare module 'react' { export function useState<T>(v?:T):[T,(x:T)=>void]; export function useEffect(f:()=>void,d:any[]):void; const React:any; export default React; }
declare module 'react-dom/client' { export function createRoot(x:any):any; }
declare module 'react/jsx-runtime';
declare module '*.css';
declare namespace JSX { interface IntrinsicElements { [key:string]: any } }
