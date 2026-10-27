# CI/CD Auralis trên AWS EC2

## Trạng thái đã xác minh ngày 27/10/2026

- Instance `i-0a87fb704efaa0ed2`, region `ap-southeast-1`, Elastic IP `52.76.1.25`.
- Kernel đang chạy `6.17.0-1017-aws`; MongoDB ping thành công.
- `mongod`, `sitechat`, `auralis-web`, `nginx` đều active; HTTPS `/`, `/login`, `/chatbot.js` trả 200.
- `/opt/sitechat` đang ở nhánh `staging`, commit `2b2a5e73c2e207610de5ba35a50d4edd4c6218c8`.
- Checkout EC2 có thay đổi `web/package-lock.json`, `web/next-env.d.ts` và dữ liệu/build chưa track. Pipeline không pull, reset hoặc clean checkout này.
- Lockfile npm trong thay đổi CI/CD được lấy từ bản đang chạy trên EC2: Next 16.4.2, React/React DOM 19.2.7.
- `backend/requirements.lock.txt` chụp 164 package đã cài trên EC2, gồm LangChain 0.3, sentence-transformers 3.4.1, transformers 4.57.6, APScheduler 3.11.3, bcrypt 4.3.0, torch 2.14.1+cpu. Đây là lock cho Linux/Python 3.12; cập nhật dependency bằng một thay đổi riêng có kiểm thử.
- SSM Agent đang active nhưng instance chưa có IAM instance profile. Chưa kích hoạt CD hoặc thay đổi service/TLS/dữ liệu trên EC2.

## Luồng hoạt động

```text
PR vào staging/main -> GitHub-hosted Ubuntu: pytest + lint + build + thử artifact
Push staging       -> cùng bộ kiểm tra -> artifact có COMMIT và SHA-256
                   -> OIDC -> S3 private -> AWS SSM -> release riêng trên EC2
                   -> readiness + HTTPS + LLM -> giữ release hoặc rollback code
```

GitHub-hosted runner thực hiện mọi job. Repo là public nên không cài runner thường trú trên máy chứa dữ liệu ứng dụng. SSM không cần mở inbound SSH cho runner; private key `auralis.pem` và `.env` không đưa vào GitHub. Security group chỉ được xác minh tên `launch-wizard-2` và socket SSH trên máy; chưa đọc được danh sách rule AWS. Thiết kế này không thay đổi rule đó.

Theo [GitHub OIDC với AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), role dùng token ngắn hạn với subject `repo:khazed-dev/auralis:environment:staging`. Environment phải chỉ cho nhánh `staging`. [SSM downloadContent](https://docs.aws.amazon.com/systems-manager/latest/userguide/documents-command-ssm-plugin-reference.html) tải artifact bằng quyền của instance profile.

CI chạy toàn bộ pytest, ESLint, Next build, thử khởi động standalone, build/check cú pháp widget và test script deploy bằng mock. E2E Playwright cũ còn phụ thuộc UI legacy nên chưa chạy; kiểm tra trình duyệt các luồng đăng nhập/crawl/handoff vẫn cần trước khi mở phát hành rộng.

## Phần được thay khi deploy

| Đường dẫn | Vai trò |
|---|---|
| `/opt/auralis/releases/<commit>-<run>-<attempt>/` | Code, venv riêng, standalone web, widget cùng commit |
| `/opt/auralis/current` | Symlink chuyển nguyên release |
| `/opt/auralis/releases/baseline` | Trỏ tới bản EC2 ban đầu, giữ thay đổi chưa commit |
| `/opt/sitechat/backend/.env` | Secrets giữ nguyên, symlink vào mỗi release |
| `/opt/sitechat/backend/data` | FAISS, uploads và dữ liệu ứng dụng giữ nguyên |
| `/opt/sitechat/backend/logs` | Log giữ ngoài release |
| `/home/ubuntu/.cache` | Cache model theo user ứng dụng, không di chuyển |
| `/opt/auralis/shared/web-cache` | Cache runtime Next/Image, ghi bởi `ubuntu`, ngoài release |
| `/var/lib/auralis-deploy/incoming` | Artifact SSM, thư mục cha do root sở hữu |

MongoDB vẫn là service `mongod`, database `sitechat`. Nginx/Certbot và các port loopback giữ cấu hình đang chạy. Embedding vẫn `BAAI/bge-m3`. Setup từ chối nếu các đường dẫn storage trong settings nằm ngoài `backend/data`; khi đó cần bổ sung symlink tương ứng trước khi chạy lại.

## 1. Chuẩn bị và khởi tạo EC2 một lần

Trước lần chuyển đầu, xác nhận backup hiện tại của MongoDB, FAISS và uploads khôi phục được. Không restore backup vào database đang chạy để thử. Giữ `/opt/sitechat` làm baseline và lưu `git status`/diff phục vụ đối chiếu; không chạy `git reset --hard` hoặc `git clean` tại đó.

Từ PowerShell, gửi script đã review tới EC2:

```powershell
& C:\Windows\System32\OpenSSH\scp.exe -i C:\Users\KHA\Downloads\auralis.pem deploy/setup-ec2.sh ubuntu@52.76.1.25:/tmp/auralis-setup-ec2.sh
& C:\Windows\System32\OpenSSH\ssh.exe -i C:\Users\KHA\Downloads\auralis.pem ubuntu@52.76.1.25 'sudo bash /tmp/auralis-setup-ec2.sh'
```

Script tạo user `auralis-deploy`, baseline, drop-in systemd và sudoers chỉ cho stop/start hai service ứng dụng, chạy LLM smoke. App tiếp tục chạy bằng `ubuntu`. Script chỉ daemon-reload, không restart service đang chạy. Lần deploy đầu mới chuyển sang release. Không chạy setup lần hai để ghi đè trạng thái đã khởi tạo.

## 2. Khởi tạo AWS bằng CloudShell hoặc AWS CLI đã đăng nhập

Tải `deploy/aws.yaml` lên CloudShell. Kiểm tra tài khoản bằng `aws sts get-caller-identity`. Nếu account đã có OIDC provider `token.actions.githubusercontent.com`, truyền ARN của provider đó qua parameter `ExistingOidcProviderArn`; không tạo provider trùng.

```bash
aws cloudformation deploy \
  --region ap-southeast-1 \
  --stack-name auralis-ci-cd \
  --template-file deploy/aws.yaml \
  --capabilities CAPABILITY_IAM

aws cloudformation describe-stacks \
  --region ap-southeast-1 --stack-name auralis-ci-cd \
  --query 'Stacks[0].Outputs' --output table
```

Stack tạo bucket private, HTTPS-only, SSE-S3 và xóa artifact sau 30 ngày; IAM OIDC role chỉ ghi prefix artifact và gọi SSM document `AuralisDeploy` trên instance đã chỉ định. Instance role có `AmazonSSMManagedInstanceCore` và quyền đọc prefix artifact. Bucket được giữ lại nếu xóa stack.

Đối chiếu lại instance profile trước khi gắn. Nếu đã có profile mới được cấu hình sau lần audit, gộp quyền SSM/S3 vào role đó thay vì ghi đè.

```bash
aws ec2 describe-iam-instance-profile-associations \
  --region ap-southeast-1 \
  --filters Name=instance-id,Values=i-0a87fb704efaa0ed2

# Chỉ dùng khi instance chưa có association; thay PROFILE_NAME bằng output stack.
aws ec2 associate-iam-instance-profile \
  --region ap-southeast-1 \
  --instance-id i-0a87fb704efaa0ed2 \
  --iam-instance-profile Name=PROFILE_NAME

aws ssm describe-instance-information \
  --region ap-southeast-1 \
  --filters Key=InstanceIds,Values=i-0a87fb704efaa0ed2 \
  --query 'InstanceInformationList[].{Id:InstanceId,State:PingStatus}'
```

Chỉ bật CD khi trạng thái là `Online`. EC2 cần outbound HTTPS tới SSM, S3, PyPI và kho CPU PyTorch. Không cần mở 3000/8000/27017 hoặc thêm rule inbound 22.

## 3. Cấu hình GitHub

Trong repository **Settings → Environments**, tạo environment `staging`, đặt **Deployment branches and tags → Selected branches and tags → staging**. Hạn chế người có quyền sửa workflow/nhánh staging. Có thể dùng required reviewer cho lần chạy đầu, sau đó bỏ nếu muốn deploy hoàn toàn tự động. Environment protection được GitHub áp dụng trước khi job deploy chạy; xem [tài liệu environment](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments).

| Vị trí | Tên | Giá trị |
|---|---|---|
| Environment `staging` → Secrets | `AWS_DEPLOY_ROLE_ARN` | Output `GitHubDeployRoleArn` |
| Environment `staging` → Variables | `ARTIFACT_BUCKET` | Output `ArtifactBucket` |
| Repository → Variables | `DEPLOY_ENABLED` | `true` sau khi setup và kiểm tra hoàn tất |

`DEPLOY_ENABLED` cần ở cấp repository vì được kiểm tra trước khi nạp environment. Không cấu hình AWS access key dài hạn, SSH private key hoặc secrets ứng dụng. `GITHUB_TOKEN` được GitHub cấp tự động và chỉ có quyền đọc contents; job deploy thêm `id-token: write` để lấy OIDC token.

Đưa thay đổi vào `staging` qua PR. CI chạy trên PR; push/merge staging tạo release mới. `workflow_dispatch` cũng chỉ deploy khi chọn staging. Workflow serialize các lần chạy cùng nhánh, không hủy deploy đang chạy; `flock` trên EC2 chặn cả deploy đồng thời từ nguồn khác. Khi CD chưa bật, CI vẫn hoạt động.

## Kiểm tra, rollback và vận hành

Preflight kiểm tra MongoDB và Nginx trước khi dừng app. Venv mới được cài từ lock và `pip check` trước khi đổi symlink; lỗi chuẩn bị không đụng service đang chạy. Sau khi đổi release, chờ tối đa 600 giây cho `/api/ready` xác nhận MongoDB ping, FAISS đã nạp và đúng commit; kiểm tra web/login/widget cùng HTTPS. Readiness không gọi LLM mỗi lần poll. Unit `auralis-smoke` thực hiện một inference giới hạn 75 giây bằng cấu hình LLM mặc định, không lưu hội thoại/quota hoặc in API key/phản hồi.

Nếu một bước sau khi dừng app thất bại, script chuyển symlink về release trước và start lại hai service. Không xóa hay restore MongoDB/FAISS/uploads. Khởi động ứng dụng hiện đã có seed/backfill trong lifespan; rollback code không đảo được thay đổi dữ liệu của những hook đó. Migration phá dữ liệu phải có quy trình riêng, không đặt trong pipeline.

```bash
readlink -f /opt/auralis/current
cat /opt/auralis/current/COMMIT
tail /opt/auralis/deployments.log
systemctl is-active mongod sitechat auralis-web nginx
curl -fsS http://127.0.0.1:8000/api/ready
sudo journalctl -u sitechat -n 100 --no-pager
sudo journalctl -u auralis-web -n 100 --no-pager
sudo journalctl -u auralis-smoke -n 30 --no-pager
```

Sau deploy đầu, thử chat trên widget của một site thật, kiểm tra câu trả lời và dữ liệu hội thoại. LLM smoke chỉ xác minh provider mặc định, chưa xác minh mọi BYOK của tenant, retrieval theo từng site hoặc luồng handoff.

Xem log thất bại theo command ID trong GitHub Actions / Systems Manager Run Command. Nếu workflow bị hủy hoặc mất kết nối, lệnh SSM có thể vẫn chạy; kiểm tra command ID và server lock trước khi thử lại. Mất điện/kill -9 không chạy được trap rollback; cần kiểm tra symlink/service sau khi máy phục hồi.

Giữ baseline và ít nhất hai release khỏe. Mỗi release có venv riêng, cần theo dõi `df -h /`; không tự động xóa release/dữ liệu trong script này. Dọn riêng các release cũ đã xác nhận không còn được dùng, giữ current và bản rollback. Có downtime ngắn khi stop/start app; chưa có blue/green hoặc zero-downtime.

## Kiểm chứng thay đổi này

- Local Windows/Python 3.12: **542 pytest passed, 6 skipped**; skip các provider tùy chọn chưa cài. Đã sửa fixture/test legacy để theo đúng phân quyền, queue crawl và UI Next hiện tại, giữ test từ chối truy cập trái quyền.
- ESLint, Next production build và standalone smoke (login, public logo, CSS) đạt; widget build và kiểm tra cú pháp hai file đầu ra đạt.
- Năm kịch bản deploy bằng mock chạy trên Ubuntu trong thư mục tạm: thành công, lỗi LLM, lỗi readiness, lỗi pip và MongoDB chưa sẵn sàng; xác nhận secrets/data sentinel còn nguyên và rollback khi cần.
- CloudFormation đạt `cfn-lint 1.58.0`; các script Bash đạt kiểm tra cú pháp.
- Trên EC2: `pip check` không có dependency hỏng; inference thực tế qua provider LLM mặc định đạt, không lưu hội thoại. Bốn service vẫn active sau kiểm tra.
- Chưa chạy workflow trên GitHub, tạo stack AWS, gắn instance profile hoặc chuyển service sang release. Clean Linux CI và deploy SSM thật cần hoàn tất các bước khởi tạo phía trên.
