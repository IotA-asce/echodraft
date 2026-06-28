import { assetUrl, type SourcePage } from "../../api";

export function ImportReview({ pages }: { pages: SourcePage[] }) {
  if (!pages.length) return null;
  return (
    <div className="import-review">
      <div className="source-heading">
        <strong>Import review</strong>
        <span>{pages.length} pages</span>
      </div>
      <div className="page-review-grid">
        {pages.map((page) => (
          <article className="page-review-card" key={page.id}>
            {page.imageUrl ? (
              <object data={assetUrl(page.imageUrl)} type="image/png" aria-label={`Page ${page.pageNumber}`} />
            ) : (
              <div className="page-placeholder">Page {page.pageNumber}</div>
            )}
            <div>
              <div className="page-review-heading">
                <strong>Page {page.pageNumber}</strong>
                <span>{page.extractionMethod.replaceAll("_", " ")}</span>
              </div>
              <p>{page.preview || "No readable text selected."}</p>
              <div className="model-meta">
                <span>{Math.round(page.confidence * 100)}% confidence</span>
                {page.warnings.length ? <span>{page.warnings.length} warnings</span> : <span>Clean</span>}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
