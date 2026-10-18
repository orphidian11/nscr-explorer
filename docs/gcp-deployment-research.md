# GCP Deployment & CI/CD Research — NSCR 3D Line Explorer

> Research only (2026-10-18). Not yet implemented. Recommendation: **Firebase Hosting (Spark free plan) + GitHub Actions with Workload Identity Federation**, deploying on new `v*` tags.

## 1. Hosting options compared

| Option | Hobby cost | Custom domain + HTTPS | Caching/SPA | Verdict |
|---|---|---|---|---|
| **Firebase Hosting** | **$0** (Spark: 10 GB storage, 360 MB/day transfer) | Free auto-provisioned SSL, one-click domain connect in console ([firebase.google.com/products/hosting](https://firebase.google.com/products/hosting)) | Global CDN; granular per-path `Cache-Control` in `firebase.json`; SPA rewrite `** -> /index.html` built in ([docs](https://firebase.google.com/docs/hosting/quickstart)) | ✅ **Best fit** |
| Cloud Storage + Cloud CDN | ~$18-25/mo — the killer is the **external Application Load Balancer forwarding rule (~$18/mo)** required for HTTPS on a custom domain, since GCS alone can't do custom-domain HTTPS ([docs](https://docs.cloud.google.com/storage/docs/hosting-static-website)) | Only via LB + managed cert | CDN cache-fill $0.01-0.02/GiB, lookups $0.0075/10k ([cloud.google.com/cdn/pricing](https://cloud.google.com/cdn/pricing)) | ❌ Overkill, costs real money |
| Cloud Run (serve static from container) | ~$0-2/mo (free tier: 2M req/mo) | Free HTTPS via `*.run.app` or LB for custom domain | Must hand-roll caching headers; cold starts | ❌ Running compute for static files is needless complexity |
| **Cloudflare Pages (alternative)** | $0 — unlimited static requests, no egress fees | Free SSL + custom domains on free plan | Built-in SPA fallback, immutable asset caching, `_headers` file | ✅ Strong runner-up — simplest option of all, but GCP was the stated preference |

## 2. Recommended stack

**Firebase Hosting on the Spark (free) plan, deployed by GitHub Actions using Workload Identity Federation.** Reasons:

- (a) genuinely $0 at hobby traffic
- (b) zero-config SSL + custom domain in the console — no load balancer, no cert management
- (c) SPA rewrites and asset cache headers are declarative in `firebase.json` (hash-busted `/assets/*` get `max-age=31536000,immutable`, `index.html` gets short cache)
- (d) deploys are atomic with instant rollback via the Firebase CLI

If you ever want to leave Google, Cloudflare Pages gives the same result with even less setup and no egress bills.

## 3. CI/CD

**Use Workload Identity Federation (keyless), not SA JSON keys.** WIF exchanges GitHub's per-run OIDC token for short-lived GCP credentials — nothing to store, leak, or rotate; Google's own docs and the `google-github-actions/auth` action state WIF is preferred over long-lived key JSON ([cloud.google.com/blog — Enabling keyless authentication from GitHub Actions](https://cloud.google.com/blog/products/identity-security/enabling-keyless-authentication-from-github-actions); [github.com/google-github-actions/auth](https://github.com/google-github-actions/auth)). A leaked SA JSON key grants access until manually rotated; a WIF token lives ~1 hour and is scoped to one repo.

Workflow trigger: `on: push: tags: ['v*']`, Node 20 + `npm ci` + `npm run build` (which is `tsc --noEmit && vite build`), then `npx firebase-tools@latest deploy --only hosting --project <ID>` — the WIF credential set by `google-github-actions/auth` is picked up via `GOOGLE_APPLICATION_CREDENTIALS`. Alternative without any GCP identity: Firebase Hosting deploy tokens (a single secret, rotatable) — acceptable fallback but WIF is cleaner.

### Sample workflow (`.github/workflows/deploy.yml`)

```yaml
name: Deploy to Firebase Hosting
on:
  push:
    tags: ['v*']        # deploy only on version tags
permissions:
  contents: read
  id-token: write       # REQUIRED for Workload Identity Federation OIDC exchange
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: npm }
      - run: npm ci
        working-directory: app        # Vite project lives in app/
      - run: npm run build            # tsc --noEmit && vite build
        working-directory: app
      - id: auth
        uses: google-github-actions/auth@v2
        with:
          project_id: ${{ secrets.GCP_PROJECT_ID }}
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: gh-deployer@${{ secrets.GCP_PROJECT_ID }}.iam.gserviceaccount.com
      - run: npx firebase-tools@latest deploy --only hosting --project "${{ secrets.GCP_PROJECT_ID }}" --non-interactive
        # firebase-tools picks up the WIF credential from GOOGLE_APPLICATION_CREDENTIALS set by the auth step
```

## 4. GCP setup checklist (user performs in console)

1. Console → create project `nscr-explorer` (pick a globally unique project ID; it's permanent). (console.cloud.google.com)
2. Link a billing account to the project (required even for free-tier Firebase features beyond Spark basics).
3. Enable APIs: `iam.googleapis.com`, `iamcredentials.googleapis.com`, `cloudresourcemanager.googleapis.com`, `firebase.googleapis.com`, `sts.googleapis.com` — or `gcloud services enable iam.googleapis.com iamcredentials.googleapis.com cloudresourcemanager.googleapis.com firebase.googleapis.com`.
4. console.firebase.google.com → 'Add project' → select the same GCP project → auto-provisions Firebase Hosting.
5. Locally: `npm i -g firebase-tools && firebase login`, then `firebase init hosting` in `E:\NSCR` — set the hosting dist dir to the Vite output (`app/dist`), configure as SPA (rewrite all to index.html). Generates `firebase.json` + `.firebaserc` (commit them; add `.firebase/` to .gitignore).
6. Create the deployer service account: `gcloud iam service-accounts create gh-deployer --project=$PROJECT_ID`.
7. Grant the minimal hosting role: `gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:gh-deployer@$PROJECT_ID.iam.gserviceaccount.com --role=roles/firebasehosting.admin`.
8. Create the WIF pool: `gcloud iam workload-identity-pools create github --location=global --project=$PROJECT_ID`.
9. Create the OIDC provider:
   ```
   gcloud iam workload-identity-pools providers create-oidc github-provider \
     --workload-identity-pool=github --location=global \
     --issuer-uri=https://token.actions.githubusercontent.com \
     --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
     --attribute-condition="assertion.repository == 'orphidian11/nscr-explorer'" \
     --project=$PROJECT_ID
   ```
   The attribute condition restricts the pool to this one repo — do not skip it.
10. Bind the identity:
    ```
    gcloud iam service-accounts add-iam-policy-binding \
      gh-deployer@$PROJECT_ID.iam.gserviceaccount.com \
      --role=roles/iam.workloadIdentityUser \
      --member='principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/orphidian11/nscr-explorer'
    ```
11. Grab the full provider resource name (`projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-provider`) — note it's the project **number**, not ID.
12. GitHub repo → Settings → Secrets and variables → Actions → add `GCP_PROJECT_ID` and `GCP_WIF_PROVIDER` (the resource name). No secret key material is stored — that's the point of WIF.
13. Commit `.github/workflows/deploy.yml` per the outline; push a tag `v0.0.1` to test end-to-end.
14. Custom domain: Firebase console → Hosting → Add custom domain → enter domain → add the DNS A/TXT records it shows → SSL auto-provisions in minutes (<24h worst case).

## 5. Cost estimate (hobby traffic, <10 GB transfer/mo, ~5-10 MB bundle)

- **Firebase Hosting (recommended): $0.** Spark free tier covers 10 GB storage + 360 MB/day transfer (~10 GB/mo); custom domain + auto-SSL included.
- Cloudflare Pages: $0 — unlimited static requests, no egress fees.
- GCS + LB + Cloud CDN: ~$20-25/mo — dominated by the forwarding-rule charge (~$18/mo) plus ~$0.08/GiB cache egress and $0.0075/10k lookups; GCS alone without HTTPS is ~$1-2/mo but only HTTP on a custom domain.
- Cloud Run: ~$0-2/mo (2M requests + 360k GiB-sec free), but cold-start latency for a pure static site.

**Total recommended stack: $0/mo** (plus ~$10-15/yr domain if not already owned).

## 6. Risks & gotchas

- **Cloud Storage custom-domain HTTPS requires an External Application Load Balancer** — the ~$18/mo forwarding rule is the single biggest cost and the reason GCS raw hosting loses to Firebase Hosting.
- **Firebase Spark-plan overage behavior**: exceeding the transfer quota takes the site offline until reset rather than auto-billing (Blaze removes the cap but enables pay-per-GB). Serving large geometry/binary datasets through the same host can blow through 360 MB/day fast — keep heavy datasets out of the bundle or upgrade to Blaze with a billing alert.
- **GCS/Firebase bucket-name confusion**: `firebase deploy` uses the Firebase Hosting CDN, not a raw GCS bucket — don't double-configure a bucket website config.
- **WIF attribute condition is mandatory**: without `assertion.repository == 'orphidian11/nscr-explorer'` any GitHub repo could mint tokens against your pool.
- **`permissions: id-token: write`** must be set on the deploy job or the OIDC token exchange fails; `actions/checkout` must run **before** `google-github-actions/auth`.
- **Local pushes on this machine need the known GCM credential-helper bypass** — CI deploy is unaffected (GitHub-side), but local tag pushes still need the workaround.
- **Cache headers**: Vite fingerprinted assets get `public,max-age=31536000,immutable`, but `index.html` must stay short-cache (Firebase default `max-age=3600`) or users get stale app versions.
- **Don't run `firebase init` into the repo root carelessly** — it writes `.firebaserc`/`firebase.json`; keep the hosting dist pointed at `app/dist` and commit the config.
- **Project ID is permanent** — pick it once.
- **CORS**: OSM raster tiles are fine client-side, but any future cross-origin data fetches need CORS headers — Firebase Hosting sets none for custom fetches; Cloudflare Pages and GCS both let you set CORS explicitly.
