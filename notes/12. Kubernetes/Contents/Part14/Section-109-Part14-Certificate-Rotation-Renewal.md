# Section 109 (Part 14): Certificate Rotation and Renewal

## 1. Definition

**Plain language:** Every internal connection in a Kubernetes cluster — kubelet talking to the API server, the API server talking to etcd, `kubectl` talking to the API server — is authenticated with an x509 certificate, and every one of those certificates has an expiration date. If they're allowed to simply expire, the components on either end of that connection stop trusting each other, and the cluster can silently grind to a halt component by component. Certificate rotation is the discipline of renewing those certificates before that happens, ideally as a routine, low-drama maintenance task rather than an emergency.

**Precise definition:** In a **kubeadm**-managed cluster, control-plane certificates (for the API server, controller-manager, scheduler, etcd, and the front-proxy) are generated at cluster creation with a default validity of **one year**, and are stored under `/etc/kubernetes/pki/`. `kubeadm certs check-expiration` reports the remaining validity of every certificate; `kubeadm certs renew <cert-name>` (or `kubeadm certs renew all`) regenerates a specific certificate (or all of them) using the existing CA, preserving the same key usage and SANs, without requiring a full `kubeadm init` from scratch. As of kubeadm's automatic behavior, **all control-plane certificates are also renewed automatically during every `kubeadm upgrade apply`** ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)), which is why clusters upgraded regularly rarely hit manual expiration. Separately, **kubelet client and serving certificates** are rotated by the **kubelet certificate rotation** feature (`--rotate-certificates`, enabled by default in modern kubeadm clusters), which requests a new certificate from the API server's `certificates.k8s.io` CertificateSigningRequest (CSR) API automatically as the current one approaches expiry, requiring no manual intervention as long as the CSR approval mechanism is functioning.

## 2. Why This Matters

- **An expired API server certificate can take down `kubectl` access and every control-plane-to-node connection simultaneously** — this is a slow-motion, entirely preventable outage, since certificate expiry dates are known in advance and can be checked proactively at any time.
- **`kubeadm upgrade apply` silently renews all control-plane certificates as a side effect** ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) — a cluster that's upgraded on a normal cadence effectively gets certificate rotation "for free," but a cluster left un-upgraded for a long stretch (beyond a year) can hit certificate expiration entirely independently of any upgrade decision.
- **This is a recurring, high-stakes CKA/CKS exam scenario** — "check certificate expiration, renew a specific certificate, restart the affected static Pod" tests exactly the kind of PKI operational competence that separates someone who understands cluster trust relationships from someone who only knows `kubectl apply`.

🔑 **Key Takeaway:** kubeadm control-plane certificates default to one-year validity and are renewed via `kubeadm certs renew` (or automatically during every `kubeadm upgrade apply`), while kubelet certificates typically self-rotate via the CSR API — but any cluster left un-upgraded and unchecked for over a year is at real risk of a preventable, cluster-wide certificate-expiry outage.

## 3. Prerequisites and Dependencies

Builds on [§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md) (Node Maintenance: cordon/drain/uncordon) — certificate renewal on a control-plane node is frequently performed during a cordoned maintenance window, since restarting the affected static Pods is a brief, deliberate disruption similar in character to other node maintenance. Back-references [§18](../Part3/Section-18-Part3-Certificates-PKI-Kubeadm-Certificate-Management.md) (Part 3, Certificates and PKI) for the foundational CA/certificate/SAN concepts this section applies operationally, and [§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) (Cluster Upgrades) for the automatic certificate renewal behavior of `kubeadm upgrade apply`. Forward-references [§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md) (Cluster Backup Strategies, Velero), since a full disaster-recovery restore onto a new or rebuilt control plane also requires re-establishing valid certificates.

## 4. Architecture Diagram

```text
   KUBEADM CERTIFICATE INVENTORY  (/etc/kubernetes/pki/)
   ═══════════════════════════════════════════════════════
   ca.crt / ca.key                    <- cluster root CA (10-year validity)
   apiserver.crt                      <- API server serving cert (1 year)
   apiserver-kubelet-client.crt       <- apiserver -> kubelet auth (1 year)
   front-proxy-ca.crt / front-proxy-client.crt   <- aggregation layer
   etcd/ca.crt, etcd/server.crt, etcd/peer.crt   <- etcd's own PKI tree (1 year)

   CHECKING EXPIRATION
   ─────────────────────────────────────────────────────────
     kubeadm certs check-expiration
       -> table: cert name | expiry date | days remaining | CA name

   MANUAL RENEWAL PATH (single cert, targeted)
   ─────────────────────────────────────────────────────────
     kubeadm certs renew apiserver
       -> new apiserver.crt generated from existing ca.crt/ca.key
       -> old cert overwritten; kubelet must restart the static Pod
          (moving the manifest out/in, or `crictl` restart) to pick it up

   AUTOMATIC RENEWAL PATH (during upgrade)
   ─────────────────────────────────────────────────────────
     kubeadm upgrade apply v1.31.0
       -> renews ALL control-plane certs as a side effect of upgrading
       -> this is why regularly-upgraded clusters rarely hit manual expiry

   KUBELET CERTIFICATE SELF-ROTATION (ongoing, background)
   ─────────────────────────────────────────────────────────
     kubelet (--rotate-certificates=true, default)
       -> as current client/serving cert nears expiry,
          kubelet automatically submits a new CSR to
          certificates.k8s.io
       -> kube-controller-manager's CSR approving controller
          (or an admin, if auto-approval isn't configured)
          approves it
       -> kubelet receives and starts using the new cert,
          with NO manual action required in the common case
```

- **The root CA (`ca.crt`/`ca.key`) has a much longer validity (10 years by default) than the leaf certificates it signs** — renewing leaf certificates does not require touching or regenerating the CA itself.
- **Renewing a certificate does not automatically restart the component using it** — the static Pod or process holding that certificate in memory must be restarted (or will pick it up on its next natural restart) before the renewal actually takes effect.

## 5. Hands-On

### 5.1 Checking Certificate Expiration

**Purpose:** Get a clear, cluster-wide view of exactly which certificates are close to expiring, before it becomes an emergency.

**Syntax:** `kubeadm certs check-expiration`

```bash
$ sudo kubeadm certs check-expiration
CERTIFICATE                    EXPIRES                  RESIDUAL TIME   CERTIFICATE AUTHORITY   EXTERNALLY MANAGED
admin.conf                     Aug 12, 2026 03:10 UTC   12d                                     no
apiserver                      Aug 12, 2026 03:10 UTC   12d             ca                      no
apiserver-etcd-client          Aug 12, 2026 03:10 UTC   12d             etcd-ca                 no
apiserver-kubelet-client       Aug 12, 2026 03:10 UTC   12d             ca                      no
controller-manager.conf        Aug 12, 2026 03:10 UTC   12d                                     no
front-proxy-client             Aug 12, 2026 03:10 UTC   12d             front-proxy-ca          no
scheduler.conf                 Aug 12, 2026 03:10 UTC   12d                                     no
etcd-healthcheck-client        Aug 12, 2026 03:10 UTC   12d             etcd-ca                 no
etcd-peer                      Aug 12, 2026 03:10 UTC   12d             etcd-ca                 no
etcd-server                    Aug 12, 2026 03:10 UTC   12d             etcd-ca                 no

CERTIFICATE AUTHORITY   EXPIRES                  RESIDUAL TIME   EXTERNALLY MANAGED
ca                       Jul 20, 2035 03:10 UTC   9y              no
etcd-ca                  Jul 20, 2035 03:10 UTC   9y              no
front-proxy-ca           Jul 20, 2035 03:10 UTC   9y              no
```

**Production usage example:** Running `kubeadm certs check-expiration` as a scheduled health check (e.g., a cron job on each control-plane node piping output to monitoring) surfaces a 12-day residual warning like the one above weeks before it becomes urgent, giving time to schedule a deliberate renewal window rather than reacting to a `kubectl` connection failure at 3 AM.

**Common errors:** Running this command as a non-root user without access to `/etc/kubernetes/pki/` fails silently or with a permissions error — `kubeadm certs check-expiration` must be run with sufficient privilege to read the certificate files directly on a control-plane node.

### 5.2 Manually Renewing Certificates

**Purpose:** Proactively renew a specific certificate (or all of them) ahead of expiration, without waiting for the next scheduled cluster upgrade.

**Syntax:** `kubeadm certs renew <cert-name>` or `kubeadm certs renew all`

```bash
$ sudo kubeadm certs renew apiserver
[renew] Reading configuration from the cluster...
certificate for serving the Kubernetes API renewed

$ sudo kubeadm certs renew all
certificate embedded in the kubeconfig file for the admin renewed
certificate for serving the Kubernetes API renewed
certificate the apiserver uses to access etcd renewed
certificate for the API server to connect to kubelet renewed
certificate embedded in the kubeconfig file for the controller manager renewed
certificate for the front proxy client renewed
certificate embedded in the kubeconfig file for the scheduler renewed
certificate for liveness probes to healthcheck etcd renewed
certificate for etcd nodes to communicate with each other renewed
certificate for serving etcd renewed

# Restart the affected static Pods so the new certs actually get loaded
$ sudo mv /etc/kubernetes/manifests/kube-apiserver.yaml /tmp/
$ sudo mv /tmp/kube-apiserver.yaml /etc/kubernetes/manifests/
# kubelet detects the manifest change and restarts the Pod with the new cert

$ sudo kubeadm certs check-expiration | grep apiserver
apiserver                      Jul 31, 2027 03:10 UTC   365d            ca                      no
```

**Production usage example:** Renewing `apiserver` and `apiserver-kubelet-client` on one control-plane node at a time, immediately after cordoning it per [§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md), minimizes the disruption window to just the brief static Pod restart, rather than renewing all control-plane certificates on every node simultaneously and risking a cluster-wide API server blip.

**Common errors:** Renewing certificates but forgetting to restart the corresponding static Pod (or wait for kubelet to pick up the manifest change) means the component keeps running with the old, still-in-memory certificate until its next natural restart — `kubeadm certs check-expiration` will report the new expiry date from disk while the running process is still using the old one, which is a common source of confusion.

### 5.3 Verifying Kubelet Certificate Self-Rotation

**Purpose:** Confirm kubelet's automatic client/serving certificate rotation is enabled and functioning, since it requires no manual renewal in the common case.

**Syntax:** `kubectl get csr` / inspect `/var/lib/kubelet/config.yaml` for `rotateCertificates`

```bash
$ grep rotateCertificates /var/lib/kubelet/config.yaml
rotateCertificates: true

$ kubectl get csr
NAME        AGE   SIGNERNAME                                    REQUESTOR                  CONDITION
csr-9f2k1   45m   kubernetes.io/kubelet-serving                 system:node:node-2         Approved,Issued
csr-8h1p3   2d    kubernetes.io/kube-apiserver-client-kubelet   system:node:node-2         Approved,Issued
```

**Production usage example:** A `kubectl get csr` showing a steady trickle of `Approved,Issued` CSRs from `system:node:<name>` requestors over time is the expected, healthy signature of kubelet certificate self-rotation working — if CSRs instead pile up in `Pending` state, the cluster's CSR auto-approval mechanism (normally handled by `kube-controller-manager`'s built-in approver for well-formed node CSRs) has stopped functioning and needs investigation before existing kubelet certificates expire.

**Common errors:** Assuming kubelet certificate rotation means control-plane certificates are also handled automatically — kubelet's `--rotate-certificates` only covers the kubelet's own client/serving certificates, not the API server, controller-manager, scheduler, or etcd certificates, which still require `kubeadm certs renew` or an upgrade to refresh.

## 6. Production Usage Notes

- **Schedule `kubeadm certs check-expiration` as a recurring monitored check on every control-plane node**, alerting well before the default one-year validity window closes, rather than discovering expiry reactively.
- **Renew certificates one control-plane node at a time in an HA cluster**, cordoning ([§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md)) each node briefly during its static Pod restart, rather than renewing and restarting all control-plane nodes' certificates simultaneously.
- **A cluster upgraded at least once within any 12-month period effectively gets free certificate renewal** via `kubeadm upgrade apply`'s side effect — clusters intentionally held on an old version for longer than that are the ones that actually need manual `kubeadm certs renew` attention.

## 7. Security Considerations

- **A leaked or overly long-lived certificate private key is a standing compromise risk** — kubeadm's default one-year validity for leaf certificates (versus the CA's decade-long validity) is a deliberate balance between operational overhead and limiting the blast radius of a potential key compromise.
- **CSR auto-approval for kubelet serving certificates should be scoped carefully** — the built-in node-authorizer-based approval flow is designed to only approve well-formed CSRs from the specific node identity requesting them; a misconfigured or overly permissive CSR approval setup could let an attacker request certificates beyond their legitimate scope.
- **`ca.key` for the cluster root CA is the single most sensitive file in the entire certificate hierarchy** — anyone possessing it can mint valid certificates for any cluster identity; it must never leave the control-plane node's protected filesystem and should be backed up ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)-adjacent concern) with the same rigor as an etcd snapshot containing Secrets.

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Cause                                                                                              | Fix                                                                                                                                           |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `kubectl` suddenly fails with an x509 "certificate has expired" error | A control-plane certificate (often `apiserver` or the admin kubeconfig cert) passed its expiry     | Run `kubeadm certs renew all`, restart affected static Pods, and regenerate `admin.conf` if needed                                            |
| Renewed certificate doesn't seem to take effect                       | The static Pod using it wasn't restarted after renewal                                             | Move the relevant manifest out of and back into `/etc/kubernetes/manifests/` to force a kubelet-triggered restart                             |
| Kubelet CSRs stuck in `Pending` indefinitely                          | CSR auto-approval mechanism in `kube-controller-manager` misconfigured or not running              | Verify controller-manager health and CSR-approving controller configuration; approve manually as a stopgap with `kubectl certificate approve` |
| `kubeadm certs renew` fails with a CA-not-found error                 | Running the command on a node without access to the relevant CA files under `/etc/kubernetes/pki/` | Run renewal on a control-plane node that actually holds the corresponding CA key material                                                     |
| Node goes `NotReady` shortly after a kubelet certificate expires      | Kubelet's client certificate to the API server expired without successful self-rotation            | Check `rotateCertificates` is enabled in kubelet config and CSR approval is functioning; manually approve pending CSRs if needed              |

## 9. Best Practices

- Monitor `kubeadm certs check-expiration` output continuously (not just when suspicious), alerting with enough lead time (weeks, not days) to schedule a calm renewal window.
- Renew and restart control-plane certificates one node at a time in HA clusters, pairing the operation with a cordon ([§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md)) for a clean, minimal-disruption maintenance window.
- Keep the cluster's `kubeadm upgrade apply` cadence ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) frequent enough that certificate renewal happens as a routine side effect, rather than letting a cluster go a full year or more without an upgrade.
- Protect `ca.key` (and the equivalent `etcd-ca` and `front-proxy-ca` keys) with the same access rigor as the most sensitive Secret in the cluster, since it's the root of trust for every certificate this section discusses.

## 10. Common Anti-Patterns / Mistakes

- **Never checking certificate expiration until `kubectl` or inter-component communication actually fails**, turning a fully preventable, scheduled maintenance task into an unplanned outage.
- **Renewing certificates but forgetting to restart the static Pods using them**, leaving the running components on old, soon-to-expire certificates despite the disk-level files being current.
- **Leaving a cluster un-upgraded for well over a year while assuming certificates "just work"**, missing that the automatic renewal side effect of `kubeadm upgrade apply` ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) is what was actually preventing expiration all along.

## 11. Interview Questions

**🎯 Beginner:** _"Why do Kubernetes certificates need to be rotated at all?"_
**Model answer:** Every certificate has an expiration date built in as a security control — it limits how long a given key pair remains valid, reducing the impact if a private key is ever compromised. In a kubeadm cluster, control-plane certificates default to one year of validity. If they're allowed to actually expire without renewal, the components relying on them — like `kubectl` authenticating to the API server, or the API server authenticating to kubelets — stop trusting each other, which can cause a cluster-wide outage. Rotation just means proactively renewing those certificates before that expiration date arrives, which is exactly what `kubeadm certs renew` does, or what happens automatically as a side effect of a `kubeadm upgrade apply`.
_What the interviewer is probing for:_ Basic understanding that certificate expiration is a real, cluster-impacting event, not an abstract PKI detail.

**🎯 Intermediate:** _"You run `kubeadm certs renew apiserver` and the command reports success, but `kubectl` still shows the old expiration date behavior. What's going on?"_
**Model answer:** `kubeadm certs renew` only writes the new certificate file to disk under `/etc/kubernetes/pki/` — it doesn't restart the API server Pod that's currently running with the old certificate loaded in memory. Since `kube-apiserver` runs as a static Pod, the fix is to force kubelet to restart it, typically by moving `kube-apiserver.yaml` out of `/etc/kubernetes/manifests/` and back in, which triggers kubelet to notice the manifest and restart the container — at which point it picks up the newly renewed certificate from disk. Running `kubeadm certs check-expiration` afterward should then show the updated, extended expiry date reflected in actual behavior.
_What the interviewer is probing for:_ Understanding that renewal and restart are two separate steps, and hands-on familiarity with the static Pod manifest restart trick.

**🎯 Senior:** _"Design a certificate rotation process for a 5-node HA control plane that minimizes disruption and avoids ever hitting an actual expiration event."_
**Model answer:** I'd run `kubeadm certs check-expiration` as a continuously monitored, alerting check across every control-plane node, with an alert threshold well before the default one-year expiry — say, 60 days out — giving ample time to schedule a deliberate maintenance window rather than reacting under pressure. I'd renew one control-plane node at a time: cordon it ([§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md)) to stop new scheduling there, run `kubeadm certs renew all` on that node, force the affected static Pods (apiserver, controller-manager, scheduler, and etcd if stacked) to restart by cycling their manifests, verify health via `etcdctl endpoint health` and `kubectl get componentstatuses`-equivalent checks, then uncordon and move to the next node — never renewing all five nodes simultaneously, since that risks a brief window where the whole control plane is restarting at once. I'd also tie this into the cluster's regular upgrade cadence ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)), since `kubeadm upgrade apply` renews certificates as a side effect — a cluster upgraded at least annually essentially gets this handled automatically, and manual renewal becomes a fallback for clusters that, for whatever reason, go longer between upgrades.
_What the interviewer is probing for:_ Ability to design a low-disruption, node-by-node procedure with proactive alerting, and awareness of how certificate renewal interacts with the broader upgrade cadence.

**🎯 Architect:** _"How should certificate lifecycle management fit into an organization's broader Kubernetes operational and disaster-recovery posture?"_
**Model answer:** I'd treat certificate expiration monitoring as a first-class, fleet-wide observability signal — not a manual per-cluster checklist — scraping `kubeadm certs check-expiration`-equivalent data (or the underlying certificate files' NotAfter dates directly) across every managed cluster into central monitoring, with alerting tiers well ahead of the one-year default validity. I'd design the renewal automation to be node-by-node and cordon-aware ([§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md)) by default, and I'd fold certificate health into the same operational cadence as upgrades ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)), since the two are mechanically linked — a cluster with a disciplined upgrade cadence rarely needs manual certificate intervention at all. For disaster recovery specifically, I'd make sure any documented cluster-rebuild runbook (standing up a new control plane from an etcd restore, per [§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md), or a from-scratch rebuild) explicitly accounts for re-establishing a valid CA and certificate set, since a restored etcd snapshot alone doesn't carry the PKI material with it in every rebuild scenario — this is precisely the kind of cross-cutting operational dependency that [§112](./Section-112-Part14-Disaster-Recovery-Planning-Kubernetes-Clusters.md)'s disaster recovery planning has to account for holistically, not certificate rotation treated as an isolated, one-off task.
_What the interviewer is probing for:_ Systems-level thinking connecting certificate lifecycle to upgrade cadence, fleet-wide monitoring, and disaster-recovery rebuild scenarios, rather than viewing certificate renewal as an isolated per-incident task.

## 12. Common Misconceptions

1. **"Renewing a certificate takes effect immediately, cluster-wide."** The new certificate is only written to disk; the component using it must be restarted (e.g., by cycling its static Pod manifest) before the renewal actually takes effect in the running process.
2. **"Kubelet's automatic certificate rotation covers all cluster certificates."** `--rotate-certificates` only handles the kubelet's own client/serving certificates — API server, controller-manager, scheduler, and etcd certificates still require `kubeadm certs renew` or an upgrade to refresh.
3. **"A one-year certificate validity means renewal only needs to happen once a year, reactively."** Proactive, monitored renewal well ahead of expiry (or reliance on a regular upgrade cadence) is what actually prevents an outage — waiting until close to the deadline removes any margin for error.
4. **"The cluster's root CA needs to be renewed as often as leaf certificates."** kubeadm's root CAs default to roughly a decade of validity, far longer than the one-year leaf certificates they sign; renewing leaf certificates does not require regenerating the CA.

## 13. 🔑 Key Takeaways

- kubeadm control-plane certificates default to one-year validity; `kubeadm certs check-expiration` reports remaining validity, and `kubeadm certs renew <name>`/`renew all` regenerates them from the existing CA.
- `kubeadm upgrade apply` ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) renews all control-plane certificates as a side effect, meaning a regularly upgraded cluster rarely needs manual renewal.
- Renewing a certificate on disk does not restart the component using it — the affected static Pod must be cycled (e.g., via its manifest) before the new certificate actually takes effect.
- Kubelet client/serving certificates typically self-rotate via the `certificates.k8s.io` CSR API (`--rotate-certificates`), independent of control-plane certificate renewal.
- Renew HA control-plane nodes one at a time, cordoning ([§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md)) each briefly, rather than renewing and restarting all nodes' certificates simultaneously.

## 14. Related Concepts & What's Next

[§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md) covered the cordon/drain/uncordon procedure that provides a clean maintenance window for exactly the kind of static Pod restarts certificate renewal requires. [§18](../Part3/Section-18-Part3-Certificates-PKI-Kubeadm-Certificate-Management.md) (Part 3) covered the foundational PKI and CA concepts this section applies operationally, and [§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) covered the cluster upgrade process whose `kubeadm upgrade apply` step renews certificates as a side effect. [§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md) (next) covers Velero-based cluster backup strategies — relevant here because a full disaster-recovery rebuild of a control plane must also account for re-establishing valid certificates and CA material, not just restoring workload state.

**Next Section:** [§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md) — `Section-110-Part14-Cluster-Backup-Strategies-Velero.md`
