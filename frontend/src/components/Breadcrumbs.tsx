import { Link } from "react-router-dom";

export type BreadcrumbItem = { label: string; to?: string };

export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return <nav aria-label="面包屑"><ol className="breadcrumbs">
    {items.map((item, index) => <li key={`${item.label}-${index}`}>
      {item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}
    </li>)}
  </ol></nav>;
}
