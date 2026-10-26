/** A stand-in for a product photo: the pet and the kind of product on a tile in the category's colour.
 *  The demo has no photographs; this keeps cards and pages looking like a shop's. */
const PET: Record<string, string> = { dog: "🐶", cat: "🐱", small_animal: "🐹", aquarium: "🐠" };
const KIND: Record<string, string> = {
  "treats": "🦴", "dental-treats": "🦷", "dry-food": "🥣", "wet-food": "🥫", "toys": "🧸",
  "accessories": "🎀", "litter": "🪣", "aquarium": "🫧", "cage": "🏠", "bedding": "🛏️",
};
const TINT = ["#E8F5EE", "#FEF6E4", "#E8F0FA", "#F5EAF7", "#FDEDEB", "#EAF4F4"];

export default function ProductImage({ petType, category, size = "card" }: {
  petType: string;
  category: string;
  size?: "card" | "page" | "thumb";
}) {
  const tint = TINT[[...category].reduce((sum, c) => sum + c.charCodeAt(0), 0) % TINT.length];
  const px = { card: 64, page: 96, thumb: 36 }[size];
  return (
    <div className={`product-image product-image-${size}`} style={{ background: tint }} role="img"
         aria-label={`${petType.replace("_", " ")} ${category.replace("-", " ")}`}>
      <span style={{ fontSize: px }}>{PET[petType] ?? "🐾"}</span>
      <span className="product-image-kind" style={{ fontSize: px * 0.38 }}>{KIND[category] ?? "🛍️"}</span>
    </div>
  );
}
