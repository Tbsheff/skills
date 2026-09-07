# Examples

## Naming ledger

```text
Nouns
  review
  chart
  collection
  packet
  generation
  account lease

Verbs
  create
  collect
  build
  publish
  open
  refresh
  report

Functions
  createChartReview()
  startChartCollection()
  runChartCollection()
  buildReviewPacket()
  publishReviewPacket()
  refreshReviewPacket()
```

## Proposed file tree

```text
apps/dashboard/
  lib/core/qa-reviews/
    chart-collection/
      start-chart-collection.ts
      get-chart-collection.ts
    review-packet/
      build-review-packet.ts
      publish-review-packet.ts

apps/integrations/
  lib/core/wellsky/chart-collection/
    run-chart-collection.ts
    collect-chart-files.ts
    write-chart-manifest.ts
    report-chart-collection.ts
```

## Call stack

```text
createQaChartReview()
  |
  +-- createReview()
  |
  +-- startQaChartReviewSaga()
        |
        +-- collectChartJob()
              |
              +-- startChartCollection()
```

## Call-flow diff

```text
createQaChartReview()
  |
- ├─ ingestPatient()
+ ├─ collectChart()
+ │  ├─ startChartCollection()
+ │  ├─ waitForChartCollection()
↳ │  └─ reportChartCollection()   MOVED
  |
  └─ startQaChartReviewSaga()
```

## API contract

```text
Dashboard                         Integrations

POST /chart-collections
--------------------------------------------->
{
  collectionRunId,
  reviewId,
  patientId,
  episodeId
}

<---------------------------------------------
202 Accepted
{
  collectionRunId,
  status: "QUEUED"
}
```

## Pseudocode

```ts
async function publishReviewPacket(input) {
  const packet = await readBuiltPacket(input.collectionRunId)

  await db.transaction(async (tx) => {
    const review = await lockReview(tx, input.reviewId)

    assert(review.status === "PREPARING")

    const files = await publishPacketFiles(tx, packet)
    await removeOldPacketFiles(tx, { reviewId: input.reviewId, keep: files })
    await openReview(tx, input.reviewId)
    await createChartReviewTask(tx, { reviewId: input.reviewId, fileIds: files.map(f => f.id) })
  })
}
```

## Failure map

```text
WellSky throttled
  -> wait and retry

optional document absent
  -> gap

worker crashes
  -> resume collection

callback fails
  -> retry report

packet build fails
  -> retry build

publication fails
  -> old packet remains live
```
