# Section 104 (Part 14): Linux in AWS/Azure/GCP (AMIs, VM Images, cloud-init)

## 1. Overview: The Golden Image Concept, Per Cloud Provider

§102 established the golden-image concept in general terms — a pre-built, fully-configured image used as the starting template for every new instance, in contrast to provisioning a bare OS live each time. Every major public cloud implements exactly that concept as its native mechanism for launching virtual machines; the underlying idea doesn't change from provider to provider, only the name and the specific API/tooling wrapped around it. This section covers that provider-specific layer, plus **cloud-init** — the piece that makes a single golden image genuinely portable and reusable across all of them.

## 2. The Same Concept, Three Names

| Provider | Native Image Concept                                |
| -------- | --------------------------------------------------- |
| AWS      | **AMI** (Amazon Machine Image)                      |
| Azure    | **VM Image** (Managed Image / Shared Image Gallery) |
| GCP      | **Machine Image** (Custom Image)                    |

Each of these is, functionally, §102's golden image applied specifically to that provider's instance-launch mechanism — a snapshot of a fully-configured disk (OS, packages, baseline configuration already in place) that the provider's compute service can boot a new instance directly from. Launching an EC2 instance from an AMI, an Azure VM from a Managed Image, or a GCP Compute Engine instance from a Machine Image are, conceptually, the identical operation described in three different provider vocabularies — none of them introduces a genuinely new idea beyond what §102 already covered; they're the same golden-image pattern with provider-specific APIs, storage mechanics, and terminology layered on top.

Each provider also has its own mechanism for sharing an image across accounts or projects and for tracking versions over time (an AMI's ID and its association with a specific account/region, an Azure Shared Image Gallery's versioned image definitions, a GCP image family that always resolves to the latest image in a related set) — the details differ, but the underlying need is the same one §102's versioning discussion (9) raised: a specific, addressable image version that a rollback or a specific launch can reliably target, rather than a vague "whatever the current image happens to be."

## 3. Marketplace/Public Images vs. Custom Images

Within any of the three providers, images come in two broad categories:

- **Marketplace or public images** — base images published by the cloud provider itself (an official "Ubuntu 22.04" AMI, for instance) or by a third-party vendor through the provider's marketplace (a pre-configured database appliance, a commercial software vendor's supported image). These are a reasonable, low-effort starting point, and for many workloads — especially early on, or for genuinely generic base OS needs — a public image plus configuration management (§98) or a lightweight cloud-init pass (4) is entirely sufficient.
- **Custom images an organization builds itself** — the direct implementation of §102's golden-image process: bake an organization's own hardening baseline, required packages, and standard configuration into an image (commonly via Packer, per §102's tool coverage), then register that resulting image as a reusable, versioned artifact in the specific cloud (an AMI registered in an AWS account, a Managed Image in an Azure subscription, a Machine Image in a GCP project). Every new instance of that role then launches from the organization's own custom image rather than from a generic public one, carrying forward all the golden-image benefits from §102 — reproducibility, faster scaling, elimination of drift.

## 4. cloud-init: Tying a Generic Image to a Specific Instance's Needs

A golden image — public or custom — is, by design, generic: it doesn't know in advance which specific hostname it'll be given, which specific SSH keys should have access, or which environment (staging vs. production) the instance being launched from it will actually join. **cloud-init** is the standard tool that closes that gap: it runs on an instance's **first boot** and applies **instance-specific configuration**, reading that configuration from cloud-provider-supplied **user data** supplied at launch time.

What cloud-init typically handles on first boot:

- **Setting the hostname** — so an instance launched from a generic image ends up with the specific hostname appropriate to its role, rather than a generic default.
- **Injecting SSH keys** — provisioning the specific public key(s) that should have access to this particular instance, supplied at launch rather than baked permanently into the image.
- **Running a startup script** — arbitrary commands supplied as part of the launch configuration, commonly used for final environment-specific setup that genuinely can't be known at image-build time.
- **Configuring network settings** — applying instance- or environment-specific networking configuration that varies by where and how the instance is being deployed.

cloud-init reads this configuration from **user data** — a block of configuration (commonly YAML, in cloud-init's own config format) that the launching tool (the AWS/Azure/GCP console, CLI, API, or — tying back to §97 — a Terraform resource definition) supplies as part of the instance-creation request. The cloud provider makes that user data available to the newly-booted instance through its metadata service, and cloud-init, running as one of the instance's very first boot-time services, reads and applies it before the instance is considered fully up.

## 5. Why cloud-init Specifically Matters

The detail that makes cloud-init worth understanding in real depth, rather than treating as a minor implementation footnote, is that it is **the same tool across AWS, Azure, GCP, and OpenStack** — it isn't an AWS-specific or Azure-specific mechanism reimplemented differently per provider. That cross-provider consistency has a direct, practical payoff: a golden image built once, with cloud-init installed and configured as part of the image, can be **launched consistently across any of these providers**, with each provider supplying its own provider-specific instance configuration as user data at launch time — without needing to maintain separate, provider-specific image variants that differ only in how they handle instance-specific first-boot setup.

> 💡 **Tip:** This is a meaningful multi-cloud or cloud-migration consideration worth surfacing proactively: an organization building golden images with cloud-init as a core, deliberate part of the image (rather than an afterthought) meaningfully reduces the work of porting a workload from one cloud to another later — the image-build pipeline and the cloud-init configuration approach carry over largely unchanged; only the provider-specific launch mechanism and the user-data content supplied at that layer need to change.

## 6. A Simple Conceptual cloud-init User-Data Example

A minimal cloud-init user-data configuration, conceptually, setting a hostname and running a package install on first boot:

```yaml
#cloud-config
hostname: app-server-03
package_update: true
packages:
  - nginx
runcmd:
  - systemctl enable nginx
  - systemctl start nginx
```

Supplied as user data at launch time, this tells cloud-init, on that specific instance's first boot: set the hostname to `app-server-03` (an instance-specific value that couldn't have been baked into a generic golden image shared by every instance of this role), refresh the package index and ensure `nginx` is installed, and run the two follow-up commands to enable and start it. The base image itself might already have most of what's needed pre-installed if it's a well-built golden image (§102) — this example deliberately keeps the first-boot work minimal, which is the pattern to aim for: the more that's genuinely universal gets pushed into the golden image at build time, the less first-boot cloud-init work (and therefore first-boot latency) every new instance has to do.

⚠️ **Warning:** User data is frequently visible via the instance's metadata service to anything running on that instance, and depending on configuration may be retrievable by anyone with sufficient access to the launch configuration itself (a Terraform state file, a launch template, a console history). Treat user data the same way §101 treated pipeline script output — never place secrets directly in cloud-init user data in plaintext; pull secrets from the provider's dedicated secrets-management service at boot time instead, tying back to Part 12's secrets management coverage (§95).

## 7. The Clean Division of Labor: Golden Image vs. cloud-init User Data

This section closes with the mental model worth carrying forward explicitly, since it resolves what could otherwise look like overlapping or competing mechanisms:

- **Golden image (§102)** = what's baked into **every** instance launched from this image, regardless of role, environment, or when it's launched — the universal baseline.
- **cloud-init user data** = what's specific to **this** instance, at **this** launch, supplied fresh each time an instance is created from that same shared image.

Everything genuinely common across every instance of a given role belongs in the golden image, built once and reused; everything that varies by instance — hostname, environment, specific keys, a final role-specific tweak — belongs in cloud-init user data, supplied at launch. Getting this division right is what makes the overall system both fast (most of the work is already done by the time an instance boots) and correctly differentiated per instance (the small remaining amount of genuinely instance-specific configuration is applied exactly where it needs to be, without requiring a separate image variant for every possible combination of hostname, environment, and role).

## 8. Hands-On: Inspecting cloud-init on a Running Instance

Confirming what cloud-init actually did on a given instance — rather than assuming the user data was applied correctly — is a common troubleshooting need when an instance boots with an unexpected hostname, missing package, or failed startup script.

### 8.1 Check cloud-init's own status and whether it completed successfully

**Purpose:** Determine whether cloud-init actually finished running on this instance, and whether any of its stages reported an error, before assuming a missing piece of expected configuration is a user-data authoring mistake rather than a cloud-init execution failure.

**Syntax:**

```bash
cloud-init status --long
```

**Example usage and expected output:**

```bash
$ cloud-init status --long
status: done
boot_status_code: enabled-by-generator
detail:
DataSourceEc2 Local (ip-10-0-1-15)
```

**Key flags:** `--long` includes the datasource detected (here, `DataSourceEc2`, confirming cloud-init correctly identified this as an AWS instance and knew where to fetch user data from) and more detail than the bare `status` output alone.

**Common errors:** Seeing `status: done` and assuming everything in the user data succeeded — `done` reports that cloud-init finished running through its stages, not that every individual command inside a `runcmd` block succeeded; a failing command inside `runcmd` is a separate thing to check (8.2).

### 8.2 Review cloud-init's own log for what user data was actually applied

**Purpose:** See the actual, detailed record of what cloud-init parsed from user data and what happened when it tried to apply each piece — the authoritative source for "why didn't my hostname/package/script change take effect" troubleshooting.

**Syntax:**

```bash
sudo cat /var/log/cloud-init-output.log
```

**Example usage and expected output:**

```bash
$ sudo cat /var/log/cloud-init-output.log
Cloud-init v. 23.4 running 'init-local' at ...
...
+ systemctl enable nginx
+ systemctl start nginx
Cloud-init v. 23.4 finished at ...
```

**Production usage example:** When an autoscaling group launches instances that come up healthy but missing an expected package or configuration, checking this log on one of the affected instances is almost always the fastest path to the root cause — a typo in the user-data YAML, a package name that doesn't exist in the image's configured repositories, or a `runcmd` step that failed partway through are all visible directly here, rather than needing to guess from the instance's resulting state alone.

**Troubleshooting:** If this log doesn't exist at all, cloud-init likely isn't installed on the image being used — a strong signal the image wasn't actually built as a proper golden image with cloud-init included (§102), or that a very minimal/custom base image was used without it, which itself is worth flagging back to whoever owns the image-build pipeline.

## 9. Common Misconceptions

1. **"AMIs, Azure VM Images, and GCP Machine Images are fundamentally different concepts requiring separate mental models."** They're the same golden-image concept (§102) with different provider-specific names and APIs — the underlying idea (a pre-built disk image used as a launch template) is identical across all three (2).
2. **"cloud-init is an AWS-specific tool, since it's most commonly discussed in AWS contexts."** It's a cross-provider standard used identically by AWS, Azure, GCP, and OpenStack — that consistency is precisely what makes a golden image portable across providers (5).
3. **"A golden image should try to bake in every possible instance-specific variation up front."** That defeats the purpose of having one reusable image — instance-specific values (hostname, environment, keys) belong in cloud-init user data supplied at launch, not duplicated as separate image variants per possible configuration (7).
4. **"User data is a safe place to put configuration, including secrets, since it's only used at boot."** User data is frequently visible via the instance metadata service and often retrievable through the launch configuration itself — secrets belong in a dedicated secrets-management service, not in plaintext user data (6's Warning).
5. **"If an instance came up healthy, cloud-init's user data was applied correctly."** `cloud-init status` reporting `done` only confirms cloud-init finished running through its stages — it doesn't confirm every individual command inside the user data actually succeeded; a failing step inside a `runcmd` block can leave an instance "healthy" by some checks while missing expected configuration, which is exactly what `/var/log/cloud-init-output.log` exists to reveal (8).

## 10. Tiered Interview Questions

**🎯 Beginner:** _"What is cloud-init, and what problem does it solve?"_
**Model answer:** cloud-init is a standard tool that runs on an instance's first boot to apply instance-specific configuration — setting the hostname, injecting SSH keys, running a startup script, configuring networking — reading that configuration from user data supplied by whoever launched the instance. It solves the problem that a golden image is, by design, generic and shared across many instances, but each specific instance still needs some configuration (like its hostname) that can't be known or baked in at image-build time.
_What the interviewer is probing for:_ Understanding cloud-init as the first-boot, instance-specific configuration layer distinct from what's baked into the image itself.

**🎯 Intermediate:** _"Why does it matter that cloud-init is the same tool across AWS, Azure, and GCP, rather than each cloud having its own separate mechanism?"_
**Model answer:** It means a golden image built once, with cloud-init installed and configured as part of the image, can be launched consistently across any of those providers — each supplies its own provider-specific user data at launch, but the image itself and the way it processes that data at first boot don't need to change per provider. Without that consistency, an organization would need to maintain separate image variants per cloud just to handle first-boot configuration differently, which adds real maintenance overhead, especially for a multi-cloud environment or a cloud migration.
_What the interviewer is probing for:_ Connecting cloud-init's cross-provider consistency to a concrete practical payoff (image portability), not just reciting that it happens to work the same way everywhere.

**🎯 Senior:** _"How do you decide what goes into the golden image versus what gets supplied via cloud-init user data at launch?"_
**Model answer:** Anything that's genuinely universal across every instance of a given role — regardless of environment, launch time, or which specific instance it is — belongs in the golden image, built once via a tool like Packer and reused. Anything that varies per instance or per launch — hostname, which environment it's joining, specific SSH keys, a final role-specific parameter — belongs in cloud-init user data, supplied fresh at launch time. The practical test is whether a value could be known at image-build time or only becomes known at instance-launch time; if it's the latter, it can't be baked in no matter how tempting it is to try, and forcing it into the image would mean maintaining separate image variants for every combination, defeating the reusability the golden image is supposed to provide. I'd also push as much as reasonably possible into the image rather than cloud-init, since first-boot cloud-init work adds to instance startup latency — the less work left for first boot, the faster new instances become usable, which matters directly for autoscaling.
_What the interviewer is probing for:_ A clear, principled division (build-time-knowable vs. launch-time-only) rather than an ad-hoc or memorized list, plus awareness of the latency trade-off.

**🎯 Architect:** _"Design an image and launch strategy for a workload that needs to run identically across AWS and Azure, with secrets supplied securely at launch."_
**Model answer:** I'd build a single Packer template (§102) targeting both an AWS AMI and an Azure Managed Image as its two output artifacts, with identical provisioning steps baking in the OS hardening baseline, required packages, and cloud-init itself as part of the image — ensuring the image content is as close to identical as each provider's underlying OS requirements allow. At launch time, I'd supply provider-specific but structurally equivalent cloud-init user data through each provider's native launch mechanism (an EC2 launch template, an Azure VM deployment), handling hostname, environment identification, and any final role-specific setup — kept minimal, per the latency reasoning in 7, since most of the real work should already be baked into the shared image. For secrets specifically, I would not place them in user data at all, given that metadata-service visibility and launch-configuration retrievability make user data an inappropriate place for anything sensitive (6's Warning) — instead, the cloud-init startup script would fetch secrets at boot time from each provider's dedicated secrets-management service (or a cross-provider secrets tool), authenticating via the instance's own identity/role rather than an embedded credential, so the golden image and cloud-init configuration stay portable and secret-free across both clouds.
_What the interviewer is probing for:_ A concrete, provider-aware design that keeps the image and cloud-init approach genuinely portable, correctly separates build-time from launch-time configuration, and treats secrets handling as a first-class design constraint rather than an afterthought.

## 11. Key Takeaways

- AWS AMIs, Azure VM Images, and GCP Machine Images are the same golden-image concept from §102, implemented with provider-specific names and APIs — not three different underlying ideas (2).
- Marketplace/public images are a reasonable starting point for generic needs; custom images are an organization's own golden image, built (commonly via Packer) and registered as a reusable artifact in a specific cloud (3).
- cloud-init runs on first boot to apply instance-specific configuration — hostname, SSH keys, startup scripts, networking — reading it from provider-supplied user data (4).
- cloud-init's cross-provider consistency (AWS/Azure/GCP/OpenStack, identically) is what makes a golden image built once genuinely portable across clouds, needing only provider-specific launch-time user data rather than separate image variants (5).
- Never place secrets directly in cloud-init user data — it's frequently visible via the instance metadata service and retrievable through the launch configuration; fetch secrets from a dedicated secrets-management service at boot instead (6's Warning).
- The clean mental model: golden image = what's baked into every instance from this image; cloud-init user data = what's specific to this instance at launch (7).

## 12. Related Concepts & What's Next

This section is the direct cloud-provider-specific continuation of §102's golden-image concept (Part 13) and depends on §97's Terraform coverage (Part 13) as the typical tool supplying user data and launching instances from these images in practice. §105, next, moves from single-instance image and boot mechanics to High Availability architectures — Pacemaker/Corosync concepts and load-balanced fleets — building on the assumption that instances are now consistently and reproducibly launched, and turning to how a fleet of them stays available as a whole.

**Next Section:** §105 — `Section-105-Part14-High-Availability-Architectures.md`
