# Section 18 (Part 3): Certificates and PKI in Kubernetes (kubeadm certificate management)

## 1. Definition

**Plain language:** Every conversation inside a Kubernetes cluster — kubelet to api-server, scheduler to api-server, one api-server replica to another, an admin's `kubectl` to the cluster — has to prove who it is before anyone trusts what it's saying. Kubernetes does this almost entirely with X.509 certificates, and kubeadm builds and wires up an entire private certificate authority the moment a cluster is born.

**Precise definition:** Kubernetes uses a **Public Key Infrastructure (PKI)** built on **X.509 certificates** to establish mutual TLS (mTLS) trust between control-plane components and clients. A **Certificate Authority (CA)** — a self-signed root certificate and its private key — signs a set of **leaf certificates**, each identifying one component (kube-apiserver, kubelet, scheduler, controller-manager, etcd, front-proxy) or one human/service identity. `kubeadm` automatically generates this entire CA hierarchy during `kubeadm init`, placing certificates and keys under `/etc/kubernetes/pki/`, and by default issues client and server certificates with a **one-year validity period**, which is why certificate rotation ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md), [§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) is an operational reality every kubeadm cluster must plan for.

## 2. Why This Matters

- **Certificate expiry is one of the most common, entirely preventable causes of full cluster outages.** An expired api-server serving certificate or an expired kubelet client certificate can silently render a cluster unreachable or un-schedulable exactly one year after bootstrap if nobody planned for renewal — this is a routine real-world incident, not a hypothetical ([§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) covers rotation during upgrades directly).
- **Every authentication decision in [§73](../Part10/Section-73-Part10-Authentication-Users-ServiceAccounts-X509-OIDC.md)–[§74](../Part10/Section-74-Part10-Authorization-Modes-RBAC-ABAC-Node-Webhook.md) ultimately traces back to a certificate issued from this PKI.** X.509 client certificate authentication is one of the core authentication methods the api-server supports, and understanding where those certificates come from is the prerequisite for understanding how they're validated.
- **CKA and CKS both test this domain heavily and expect hands-on fluency**, not just conceptual awareness — `kubeadm certs check-expiration`, `kubeadm certs renew`, and manual `openssl` inspection of certificate fields are realistic exam tasks ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) covers CKS-level certificate rotation depth and hardening beyond this section's baseline).

🔑 **Key Takeaway:** kubeadm builds a full private CA at cluster bootstrap and issues one-year certificates for every control-plane component by default — treating certificate expiry as a routine, monitored maintenance task (not a surprise) is the single biggest practical lesson of this section.

## 3. Prerequisites and Dependencies

Builds on [§16](./Section-16-Part3-Kubeadm-Cluster-Bootstrapping-Step-By-Step.md) (kubeadm init, which is the exact moment this entire PKI is generated) and [§8](../Part2/Section-08-Part2-Control-Plane-Components.md) (control plane components, since each certificate here identifies one of those five components). No external prerequisites beyond basic TLS/certificate concepts.

## 4. PKI Architecture Diagram

```text
                         ┌──────────────────────────────────┐
                         │   Kubernetes Cluster Root CA     │
                         │   ca.crt / ca.key                │
                         │   (self-signed, 10-year validity)│
                         └───────────────┬──────────────────┘
                                         │ signs
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌────────────────────┐         ┌──────────────────────┐          ┌────────────────────────┐
│ apiserver.crt/key  │         │ apiserver-kubelet-   │          │ front-proxy-ca.crt     │
│ (api-server serving│         │ client.crt/key       │          │ (separate CA for       │
│ cert; SANs include │         │ (api-server's client │          │  aggregation layer /   │
│ cluster IP, node   │         │  identity when it    │          │  extension API servers)│
│ IPs, DNS names)    │         │  calls kubelets)     │          └────────────────────────┘
└────────────────────┘         └──────────────────────┘
        │                                │
        ▼                                ▼
┌────────────────────────┐         ┌─────────────────────┐
│ scheduler.conf         │         │ controller-manager. │      ┌───────────────────────┐
│ (kube-scheduler's      │         │ conf (its client id)│      │  etcd/ca.crt          │
│ client cert/kubeconfig)│         └─────────────────────┘      │  (SEPARATE CA — its   │
└────────────────────────┘                                      │  own trust root for   │
                                                                │  etcd peer/client TLS)│
                                                                └───────────────────────┘
```

- **There are actually two independent CAs in a default kubeadm cluster**, not one: the main Kubernetes CA (`/etc/kubernetes/pki/ca.crt`) trusted by the api-server and all control-plane clients, and a separate **etcd CA** (`/etc/kubernetes/pki/etcd/ca.crt`) trusted only within the etcd peer/client trust boundary — compromising one does not automatically compromise the other.
- **A third CA, the front-proxy CA**, exists specifically for the API aggregation layer (extension API servers, e.g., the metrics server) — kept separate so a compromised aggregated API server cannot forge identities trusted by the main cluster CA.
- Every leaf certificate embeds **Subject Alternative Names (SANs)** — for the api-server's serving certificate, this includes the cluster's Service IP, all control-plane node IPs/hostnames, and `kubernetes.default.svc` — which is why adding a new load-balancer front-end or control-plane node after the fact requires regenerating that certificate with updated SANs.

## 5. Hands-On: Inspecting and Managing kubeadm's PKI

### 5.1 `kubeadm certs check-expiration` — Auditing Certificate Lifetimes

**Purpose:** The single most useful day-one command for any kubeadm cluster — lists every managed certificate and exactly when it expires.

**Syntax:**

```bash
kubeadm certs check-expiration
```

**Example usage and expected output:**

```bash
$ sudo kubeadm certs check-expiration
CERTIFICATE                    EXPIRES                  RESIDUAL TIME   CERTIFICATE AUTHORITY   EXTERNALLY MANAGED
admin.conf                     Jul 30, 2027 09:12 UTC    364d            ca                      no
apiserver                      Jul 30, 2027 09:12 UTC    364d            ca                      no
apiserver-etcd-client          Jul 30, 2027 09:12 UTC    364d            etcd-ca                 no
apiserver-kubelet-client       Jul 30, 2027 09:12 UTC    364d            ca                      no
controller-manager.conf        Jul 30, 2027 09:12 UTC    364d            ca                      no
etcd-healthcheck-client        Jul 30, 2027 09:12 UTC    364d            etcd-ca                 no
etcd-peer                      Jul 30, 2027 09:12 UTC    364d            etcd-ca                 no
etcd-server                    Jul 30, 2027 09:12 UTC    364d            etcd-ca                 no
front-proxy-client             Jul 30, 2027 09:12 UTC    364d            front-proxy-ca          no
scheduler.conf                 Jul 30, 2027 09:12 UTC    364d            ca                      no

CERTIFICATE AUTHORITY   EXPIRES                  RESIDUAL TIME   EXTERNALLY MANAGED
ca                      Jul 28, 2036 09:12 UTC    9y              no
etcd-ca                 Jul 28, 2036 09:12 UTC    9y              no
front-proxy-ca          Jul 28, 2036 09:12 UTC    9y              no
```

**Production usage example:** This command should be wired into a scheduled monitoring check (a cron job piping the output into an alert, or a dedicated exporter) so operators get advance warning weeks before any certificate crosses its expiry — not a 3 AM page when the api-server refuses connections because its serving cert expired.

**Common errors:** Running this without `sudo`/root often fails silently or with a permission error, since `/etc/kubernetes/pki/` is root-owned by design — always run certificate commands with appropriate privilege on the control-plane node.

### 5.2 `kubeadm certs renew` — Manual Certificate Renewal

**Purpose:** Regenerates one or all kubeadm-managed certificates, re-signed by the existing CA, extending their validity roughly another year from the renewal date.

**Syntax:**

```bash
kubeadm certs renew all
kubeadm certs renew apiserver
```

**Example usage and expected output:**

```bash
$ sudo kubeadm certs renew all
[renew] Reading configuration from the cluster...
certificate embedded in the kubeconfig file for the admin to use and for kubeadm itself renewed
certificate for serving the Kubernetes API renewed
certificate the apiserver uses to access etcd renewed
certificate for the API server to connect to kubelet renewed
certificate embedded in the kubeconfig file for the controller manager to use renewed
certificate for liveness probes to healthcheck etcd renewed
certificate for etcd nodes to communicate with each other renewed
certificate for serving etcd renewed
certificate for the front proxy client renewed
certificate embedded in the kubeconfig file for the scheduler manager to use renewed
```

**Production usage example:** After renewal, the static Pod manifests under `/etc/kubernetes/manifests/` don't need editing (they reference the same file paths), but the kubelet must pick up the new files — a `systemctl restart kubelet` on the control-plane node is typically required for control-plane static Pods to actually load the renewed certificates. This exact procedure is exercised in depth as part of cluster upgrades ([§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)).

**Common errors:** Forgetting to restart the affected static Pods (by restarting kubelet, or deleting the Pod manifest briefly) after renewal — the on-disk certificate files change, but running processes keep using the certificate they loaded at startup until restarted.

### 5.3 Manually Inspecting a Certificate With `openssl`

**Purpose:** When you need to verify exactly what a certificate claims — its SANs, expiry, or issuing CA — independent of kubeadm's own tooling (useful for troubleshooting or for CKS-style manual verification tasks).

```bash
$ sudo openssl x509 -in /etc/kubernetes/pki/apiserver.crt -noout -text | grep -A2 "Validity\|Subject Alternative"
        Validity
            Not Before: Jul 31 09:12:03 2026 GMT
            Not After : Jul 30 09:12:03 2027 GMT
            X509v3 Subject Alternative Name:
                DNS:kubernetes, DNS:kubernetes.default, DNS:kubernetes.default.svc,
                DNS:kubernetes.default.svc.cluster.local, DNS:control-plane-01,
                IP Address:10.96.0.1, IP Address:192.168.1.10
```

**Production usage example:** After adding a new load-balancer VIP in front of a multi-control-plane cluster, this command is exactly how you'd confirm whether that new VIP is (or isn't yet) included in the api-server certificate's SAN list — a missing SAN produces TLS handshake failures for any client connecting via the new address, requiring regeneration with an updated `ClusterConfiguration` before the LB can be trusted.

## 6. Production Usage Notes

- **Certificates for `kubeadm`-managed clusters expire in exactly one year by default**, and this is a deliberate, well-known operational gotcha — teams that bootstrap a cluster and don't touch it again for 13 months routinely discover the api-server has stopped accepting connections.
- **Since kubeadm 1.15+, control-plane certificates are automatically renewed during `kubeadm upgrade apply`**, which is one of the strongest practical reasons to keep a kubeadm cluster on a regular upgrade cadence rather than treating upgrades and certificate renewal as separate concerns.
- **kubelet client certificates use a different, self-renewing mechanism** — kubelet-managed certificates via the `certificates.k8s.io` API are automatically rotated well before expiry when `--rotate-certificates` is enabled (the kubeadm default on worker nodes), which is a materially different lifecycle from the manually-renewed static control-plane certificates covered above.
- **The root CA itself has a much longer default lifetime (10 years)** specifically so that routine leaf-certificate renewal never requires re-establishing cluster-wide trust — only a genuine CA compromise or an intentional re-key would require rotating the CA itself.

## 7. Security Considerations

- **Compromise of `ca.key` is equivalent to full and permanent cluster compromise** — anyone holding that private key can mint a certificate for any identity, including `system:masters` cluster-admin. It should be treated with the same sensitivity as root cloud credentials, stored with restrictive filesystem permissions, and ideally kept offline or in an HSM for high-security environments ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) covers hardening this further).
- **The separate etcd CA is a deliberate blast-radius boundary** — a compromised kubelet or api-server client certificate does not, by itself, grant access to etcd's peer/client trust domain, and this separation should never be collapsed for convenience.
- **Certificates issued to human users (e.g., `admin.conf`) typically carry long-lived client certificates with no built-in revocation mechanism** in vanilla Kubernetes X.509 auth — this is why production clusters are strongly encouraged to layer OIDC or another externally revocable identity provider on top of raw client-cert authentication for human access ([§73](../Part10/Section-73-Part10-Authentication-Users-ServiceAccounts-X509-OIDC.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                                                                     | Resolution Path                                                                                                                       |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| api-server suddenly unreachable, cluster was untouched for over a year | api-server (or another control-plane) certificate expired                                                                        | `kubeadm certs check-expiration`, then `kubeadm certs renew all` and restart affected static Pods/kubelet                             |
| `kubectl` reports `x509: certificate signed by unknown authority`      | Client kubeconfig's embedded CA data doesn't match the cluster's current CA (e.g., after a CA rotation or wrong kubeconfig file) | Re-fetch a correct `admin.conf` from the control-plane node; verify `certificate-authority-data` matches `/etc/kubernetes/pki/ca.crt` |
| New load-balancer/VIP in front of control plane fails TLS handshake    | api-server certificate's SANs don't include the new address                                                                      | Regenerate the api-server certificate with the new SAN via updated `ClusterConfiguration` and `kubeadm init phase certs apiserver`    |
| Renewed certificates on disk but component still rejects connections   | Static Pod/process hasn't reloaded the renewed certificate files                                                                 | Restart kubelet (control-plane static Pods) or the specific component process to force reload                                         |

## 9. Best Practices

- Monitor certificate expiration proactively (`kubeadm certs check-expiration` on a schedule, or an exporter feeding alerting) rather than discovering expiry reactively during an outage.
- Keep kubeadm clusters on a regular upgrade cadence, since `kubeadm upgrade apply` renews control-plane certificates automatically as a side effect — this turns certificate renewal into a solved problem rather than a separate manual chore.
- Back up `/etc/kubernetes/pki/` (particularly the CA key material) as part of any cluster backup strategy — losing the CA without a backup means every component's trust relationship must be rebuilt from scratch.

## 10. Common Anti-Patterns / Mistakes

- **Bootstrapping a cluster and never revisiting certificate lifetimes** — the default one-year validity is a ticking clock, not a "set and forget" configuration.
- **Manually copying certificate files between nodes or environments** instead of using kubeadm's own generation/renewal tooling, which frequently produces SAN mismatches or trust chain breaks that are painful to diagnose.
- **Treating the etcd CA and the main cluster CA as interchangeable** or storing them without the same access boundary — they exist as separate trust domains specifically to limit blast radius, and conflating them defeats that design.

## 11. Interview Questions

**🎯 Beginner:** _"What is the default validity period for kubeadm-issued certificates, and why does that matter operationally?"_
**Model answer:** kubeadm issues most component certificates with a default one-year validity. This matters because a cluster that's bootstrapped and then left untouched can suffer a complete outage roughly a year later when the api-server's (or another component's) certificate expires and TLS handshakes start failing cluster-wide — so certificate expiry needs to be actively monitored, not assumed to be a non-issue.
_What the interviewer is probing for:_ Basic awareness that certificates aren't permanent and that this is a real, recurring operational responsibility.

**🎯 Intermediate:** _"Walk me through how you'd safely renew all certificates on a kubeadm cluster approaching expiry."_
**Model answer:** I'd first run `kubeadm certs check-expiration` to confirm which certificates are actually close to expiring and get a clear picture before touching anything. Then I'd run `kubeadm certs renew all` on each control-plane node, which regenerates the certificate files signed by the existing CA. Since the running static Pods and kubelet have already loaded the old certificates into memory, I'd then restart the kubelet service on each control-plane node (or briefly move the static Pod manifests to force a restart) so the renewed files actually get picked up. Finally I'd re-verify with `check-expiration` that the new expiry dates are in place, and confirm `kubectl` connectivity is healthy afterward.
_What the interviewer is probing for:_ Hands-on procedural fluency, not just conceptual awareness — specifically remembering that renewal alone isn't enough without a restart to reload the new files.

**🎯 Senior:** _"Explain why kubeadm creates a separate CA for etcd instead of reusing the main cluster CA."_
**Model answer:** It's a deliberate blast-radius containment decision. etcd holds the entire cluster's raw state, including Secrets, and its peer and client TLS trust is arguably even more sensitive than the main api-server's trust domain. If etcd used the same CA as everything else, any certificate capable of authenticating as a normal cluster client (or any process able to mint certificates from that shared CA) could potentially also gain trusted access to etcd directly, bypassing the api-server's authorization and admission control entirely. Keeping etcd's CA separate means a compromise of the main cluster CA doesn't automatically imply etcd compromise, and vice versa — the two trust domains have to be breached independently.
_What the interviewer is probing for:_ Understanding of PKI segmentation as a genuine security design decision, not an arbitrary implementation detail.

**🎯 Architect:** _"You're designing certificate lifecycle management for a fleet of dozens of independently-bootstrapped kubeadm clusters across an organization. What would you build, and what failure mode are you specifically trying to prevent?"_
**Model answer:** I'd build a centralized monitoring layer that runs `kubeadm certs check-expiration` (or equivalent direct `openssl` inspection) against every cluster on a schedule, feeding a dashboard and alerting pipeline with a meaningfully long lead time — weeks, not days — before any certificate's expiry. I'd also push hard for every cluster to be on an enforced, regular `kubeadm upgrade` cadence specifically because certificate renewal happens automatically as a side effect of upgrades, turning what would otherwise be dozens of independent manual renewal processes into a single well-tested upgrade workflow. Separately, I'd ensure CA private key material for every cluster is backed up securely (and access-controlled distinctly from operational credentials) as part of disaster recovery planning. The failure mode I'm specifically preventing is the scenario where a handful of lower-visibility clusters — an old staging environment, a satellite regional cluster nobody actively watches — silently cross their one-year certificate boundary and suffer a full, surprising outage, discovered only when someone tries to use them and finds `kubectl` completely refusing connections.
_What the interviewer is probing for:_ Ability to scale a per-cluster operational concern into fleet-wide, proactive governance, and to connect certificate hygiene to broader upgrade and disaster-recovery discipline.

## 12. Common Misconceptions

1. **"Kubernetes has one single certificate authority."** A default kubeadm cluster actually has at least three: the main cluster CA, a separate etcd CA, and a separate front-proxy CA, each bounding a distinct trust domain.
2. **"Renewing certificates on disk is enough."** Running processes and static Pods keep using whatever certificate they loaded at startup — a restart (kubelet restart, or forcing the static Pod to reload) is required for renewal to actually take effect.
3. **"Kubelet certificates and control-plane certificates renew the same way."** Kubelet client certificates typically self-rotate automatically via `certificates.k8s.io` when `--rotate-certificates` is enabled; static control-plane certificates require explicit `kubeadm certs renew` or an upgrade to refresh.
4. **"The CA's own long lifetime means certificate management is a non-issue."** The 10-year root CA lifetime is intentionally long precisely because the _leaf_ certificates it signs are short-lived (one year) and need regular attention — the long CA lifetime is not evidence that nothing needs monitoring.

## 13. 🔑 Key Takeaways

- kubeadm builds a full X.509 PKI at bootstrap time, with the main cluster CA, a separate etcd CA, and a separate front-proxy CA each bounding a distinct trust domain.
- Most leaf certificates default to a one-year validity, making proactive expiry monitoring (`kubeadm certs check-expiration`) a mandatory operational habit, not an optional nicety.
- `kubeadm certs renew` regenerates certificates but requires a subsequent restart (kubelet or static Pod reload) to actually take effect on running components.
- `kubeadm upgrade apply` renews control-plane certificates automatically as a side effect, making a regular upgrade cadence one of the most effective certificate-management strategies available.
- The CA private key (`ca.key`) is equivalent to full cluster trust — its compromise is a total breach, and it must be protected and backed up with commensurate rigor.

## 14. Related Concepts & What's Next

This section built directly on [§16](./Section-16-Part3-Kubeadm-Cluster-Bootstrapping-Step-By-Step.md)'s `kubeadm init` (the moment this PKI is first generated) and [§8](../Part2/Section-08-Part2-Control-Plane-Components.md)'s control-plane component map (since each certificate identifies one of those components). It underpins the client-certificate authentication mechanism covered in depth in [§73](../Part10/Section-73-Part10-Authentication-Users-ServiceAccounts-X509-OIDC.md)–[§74](../Part10/Section-74-Part10-Authorization-Modes-RBAC-ABAC-Node-Webhook.md), and is revisited both during routine cluster upgrades in [§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) and at CKS hardening depth in [§109](../Part14/Section-109-Part14-Certificate-Rotation-Renewal.md) and [§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md). [§19](./Section-19-Part3-Joining-Nodes-Bootstrap-Tokens.md) (next) covers how a fresh node uses a short-lived bootstrap token — a related but distinct trust mechanism — to join a cluster and obtain its own kubelet certificate for the first time.

**Next Section:** [§19](./Section-19-Part3-Joining-Nodes-Bootstrap-Tokens.md) — `Section-19-Part3-Joining-Nodes-Bootstrap-Tokens.md`
