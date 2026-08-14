import{c,j as s,e as i}from"./index-z5ZMzs9f.js";/**
 * @license lucide-react v0.462.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const r=c("ChevronLeft",[["path",{d:"m15 18-6-6 6-6",key:"1wnfg3"}]]);/**
 * @license lucide-react v0.462.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const o=c("ChevronRight",[["path",{d:"m9 18 6-6-6-6",key:"mthhwq"}]]);function x({page:e,pageSize:h,total:t,onPage:n}){const a=Math.max(1,Math.ceil(t/h));return s.jsxs("div",{className:"mt-4 flex items-center justify-between text-sm text-zinc-500",children:[s.jsxs("span",{children:["Page ",e," of ",a," (",t," total)"]}),s.jsxs("div",{className:"flex gap-2",children:[s.jsxs(i,{variant:"ghost",disabled:e<=1,onClick:()=>n(e-1),children:[s.jsx(r,{className:"h-4 w-4"})," Prev"]}),s.jsxs(i,{variant:"ghost",disabled:e>=a,onClick:()=>n(e+1),children:["Next ",s.jsx(o,{className:"h-4 w-4"})]})]})]})}export{x as P};
