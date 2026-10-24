/** "+1 variant": this row stands for other SKUs of the same name and details
 *  (the generated catalogue repeats some names). The row is the SKU Aito
 *  ranked highest; the others' scores aren't added to it (src/same_name.py). */
export default function VariantNote({ skus }: { skus: string[] }) {
  if (skus.length === 0) return null;
  return (
    <span className="card-sub" style={{ fontSize: 11, marginRight: 6 }}
          title={`Same name and details as ${skus.join(", ")}. Shown once, as the SKU Aito ranked highest.`}>
      +{skus.length} variant{skus.length > 1 ? "s" : ""}
    </span>
  );
}
