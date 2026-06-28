import { useState } from "react";

export function ReferenceForm({
  label,
  placeholder,
  items,
  onSubmit,
}: {
  label: string;
  placeholder: string;
  items: string[];
  onSubmit: (value: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  return (
    <div className="reference-card">
      <strong>{label}</strong>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (value.trim()) void onSubmit(value.trim()).then(() => setValue(""));
        }}
      >
        <input placeholder={placeholder} value={value} onChange={(event) => setValue(event.target.value)} />
        <button>Add</button>
      </form>
      {items.map((item) => (
        <small key={item}>{item}</small>
      ))}
    </div>
  );
}
