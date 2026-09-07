# Worked Examples

These examples are canonical reference cases for the skill.

## Example 1: Closed domain variants — use a discriminated union

### Before
```ts
abstract class Order {
  abstract total(): number;
}

class PendingOrder extends Order {
  constructor(private readonly items: { price: number; qty: number }[]) {
    super();
  }

  total() {
    return this.items.reduce((sum, item) => sum + item.price * item.qty, 0);
  }
}

class CancelledOrder extends Order {
  total() {
    return 0;
  }
}

class PaidOrder extends Order {
  constructor(
    private readonly items: { price: number; qty: number }[],
    private readonly paidAt: Date,
  ) {
    super();
  }

  total() {
    return this.items.reduce((sum, item) => sum + item.price * item.qty, 0);
  }
}
```

### After
```ts
type LineItem = { price: number; qty: number };

type Order =
  | { kind: "pending"; items: LineItem[] }
  | { kind: "cancelled"; reason: string }
  | { kind: "paid"; items: LineItem[]; paidAt: Date };

function orderTotal(order: Order): number {
  switch (order.kind) {
    case "pending":
    case "paid":
      return order.items.reduce((sum, item) => sum + item.price * item.qty, 0);
    case "cancelled":
      return 0;
    default: {
      const _exhaustive: never = order;
      return _exhaustive;
    }
  }
}
```

### Why this is better
- The cases are closed and naturally modeled as data.
- Exhaustiveness is explicit.
- Runtime objects with inheritance were not buying meaningful identity or lifecycle.

---

## Example 2: External boundary — use an interface plus adapter

### Before
```ts
import Stripe from "stripe";

class CheckoutService {
  constructor(private readonly stripe: Stripe) {}

  async charge(customerId: string, amountCents: number) {
    return this.stripe.paymentIntents.create({
      amount: amountCents,
      currency: "usd",
      customer: customerId,
      confirm: true,
    });
  }
}
```

### After
```ts
type ChargeRequest = {
  customerId: string;
  amountCents: number;
  currency: "usd" | "eur";
};

type ChargeResult =
  | { kind: "approved"; providerRef: string }
  | { kind: "declined"; reason: string };

interface PaymentGateway {
  charge(request: ChargeRequest): Promise<ChargeResult>;
}

class StripePaymentGateway implements PaymentGateway {
  constructor(private readonly stripe: Stripe) {}

  async charge(request: ChargeRequest): Promise<ChargeResult> {
    const result = await this.stripe.paymentIntents.create({
      amount: request.amountCents,
      currency: request.currency,
      customer: request.customerId,
      confirm: true,
    });

    if (result.status === "succeeded") {
      return { kind: "approved", providerRef: result.id };
    }

    return {
      kind: "declined",
      reason: result.last_payment_error?.message ?? "Unknown decline",
    };
  }
}

class CheckoutService {
  constructor(private readonly payments: PaymentGateway) {}

  charge(customerId: string, amountCents: number) {
    return this.payments.charge({ customerId, amountCents, currency: "usd" });
  }
}
```

### Why this is better
- Vendor complexity is isolated.
- Internal code depends on stable semantics.
- A test double or second provider can now slot in cleanly.

---

## Example 3: Stateless strategy — use functions, not classes

### Before
```ts
interface PriceStrategy {
  apply(basePrice: number): number;
}

class BlackFridayPriceStrategy implements PriceStrategy {
  apply(basePrice: number) {
    return basePrice * 0.7;
  }
}

class VipPriceStrategy implements PriceStrategy {
  apply(basePrice: number) {
    return basePrice * 0.85;
  }
}
```

### After
```ts
type PriceStrategy = (basePrice: number) => number;

const blackFriday: PriceStrategy = basePrice => basePrice * 0.7;
const vipDiscount: PriceStrategy = basePrice => basePrice * 0.85;

function priceWith(strategy: PriceStrategy, basePrice: number) {
  return strategy(basePrice);
}
```

### Why this is better
- No identity or lifecycle exists here.
- Functions compose and test more easily.
- The abstraction matches the actual problem: interchangeable behavior.

---

## Example 4: Abstract factory is actually justified

### Problem
The system needs a coordinated family of services for `prod`, `sandbox`, and `test`.
Each environment must produce matching implementations of:
- `PaymentGateway`
- `AuditLog`
- `WebhookVerifier`

### Good shape
```ts
interface PaymentGateway {
  charge(amountCents: number): Promise<void>;
}

interface AuditLog {
  record(event: string): Promise<void>;
}

interface WebhookVerifier {
  verify(signature: string, payload: string): boolean;
}

interface BillingServices {
  paymentGateway(): PaymentGateway;
  auditLog(): AuditLog;
  webhookVerifier(): WebhookVerifier;
}

class ProdBillingServices implements BillingServices {
  paymentGateway() {
    return new StripeGateway();
  }
  auditLog() {
    return new DatadogAuditLog();
  }
  webhookVerifier() {
    return new StripeWebhookVerifier();
  }
}

class TestBillingServices implements BillingServices {
  paymentGateway() {
    return new FakeGateway();
  }
  auditLog() {
    return new InMemoryAuditLog();
  }
  webhookVerifier() {
    return new PermissiveWebhookVerifier();
  }
}
```

### Why this is justified
- The choice is about a *family* of related collaborators.
- The family is selected at runtime.
- The collaborators must stay compatible.

---

## Example 5: Builder is justified only when construction is staged

### Before
```ts
type ReportRequest = {
  teamId?: string;
  from?: string;
  to?: string;
  format?: "csv" | "json";
  includeArchived?: boolean;
};

function runReport(request: ReportRequest) {
  if (!request.teamId || !request.from || !request.to) {
    throw new Error("Missing required fields");
  }
}
```

### After
```ts
class ReportRequestBuilder {
  private teamId?: string;
  private from?: string;
  private to?: string;
  private format: "csv" | "json" = "json";
  private includeArchived = false;

  forTeam(teamId: string) {
    this.teamId = teamId;
    return this;
  }

  between(from: string, to: string) {
    this.from = from;
    this.to = to;
    return this;
  }

  as(format: "csv" | "json") {
    this.format = format;
    return this;
  }

  withArchived() {
    this.includeArchived = true;
    return this;
  }

  build() {
    if (!this.teamId || !this.from || !this.to) {
      throw new Error("teamId and date range are required");
    }

    return {
      teamId: this.teamId,
      from: this.from,
      to: this.to,
      format: this.format,
      includeArchived: this.includeArchived,
    };
  }
}
```

### Why this is justified
- Construction is staged.
- Validation belongs to the build step.
- There is real value in preventing partial request objects from leaking.

---

## Example 6: Boolean soup — use a state model

### Before
```ts
type UploadModel = {
  isIdle: boolean;
  isUploading: boolean;
  isSuccess: boolean;
  hasError: boolean;
  errorMessage?: string;
};
```

### After
```ts
type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; progress: number }
  | { kind: "success"; fileId: string }
  | { kind: "error"; message: string };
```

### Why this is better
- Impossible combinations disappear.
- UI rendering and behavior become easier to reason about.
- Exhaustive handling becomes possible.

---

## Example 7: Factory function beats factory class

### Before
```ts
class HttpClientFactory {
  create() {
    return new HttpClient({
      timeoutMs: 5_000,
      retries: 2,
    });
  }
}
```

### After
```ts
function createHttpClient() {
  return new HttpClient({
    timeoutMs: 5_000,
    retries: 2,
  });
}
```

### Why this is better
- There was no family selection, configuration object lifetime, or shared factory behavior.
- A function says exactly what is happening.

---

## Example 8: Runtime validation is not a type alias

### Before
```ts
type User = {
  id: string;
  email: string;
};

async function readUser(): Promise<User> {
  return await fetch("/api/user").then(r => r.json());
}
```

### After
```ts
type User = {
  id: string;
  email: string;
};

function isUser(value: unknown): value is User {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof (value as { id: unknown }).id === "string" &&
    "email" in value &&
    typeof (value as { email: unknown }).email === "string"
  );
}

async function readUser(): Promise<User> {
  const value: unknown = await fetch("/api/user").then(r => r.json());

  if (!isUser(value)) {
    throw new Error("Invalid user payload");
  }

  return value;
}
```

### Why this matters
- TypeScript types do not validate runtime input.
- External data is a trust boundary.
