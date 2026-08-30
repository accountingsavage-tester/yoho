"use client";

import { usePathname, useRouter } from "next/navigation";

export default function BackButton(){
  const pathname=usePathname();
  const router=useRouter();
  if(pathname==="/") return null;
  return <button className="yoho-back" onClick={()=>{if(window.history.length>1) router.back(); else router.push("/")}} aria-label="Go back">← <span>Back</span></button>;
}
