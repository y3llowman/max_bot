import { useEffect, useRef } from "react";

export function useDockHeight<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const root = document.documentElement.style;
    const update = () => root.setProperty("--dock", `${el.offsetHeight}px`);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      ro.disconnect();
      root.setProperty("--dock", "0px");
    };
  }, []);
  return ref;
}
