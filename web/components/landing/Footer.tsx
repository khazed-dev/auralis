const groups = [
  { title: "Sản phẩm", links: ["Tính năng", "Bảng giá", "Tích hợp", "Nhật ký cập nhật"] },
  { title: "Công ty", links: ["Về chúng tôi", "Tuyển dụng", "Blog", "Liên hệ"] },
  { title: "Hỗ trợ", links: ["Trung tâm trợ giúp", "Tài liệu API", "Trạng thái hệ thống"] },
  { title: "Pháp lý", links: ["Chính sách bảo mật", "Điều khoản dịch vụ"] },
];

export function Footer() {
  return (
    <footer>
      <div className="container footer-grid">
        <div className="footer-about">
          <strong>Auralis</strong>
          <p>Trợ lý AI chăm sóc khách hàng thông minh, vận hành bằng công nghệ RAG tiên tiến.</p>
          <small>© {new Date().getFullYear()} Auralis AI. Bảo lưu mọi quyền.</small>
        </div>
        {groups.map((group) => (
          <div className="footer-group" key={group.title}>
            <strong>{group.title}</strong>
            {group.links.map((link) => (
              <a href="#" key={link}>
                {link}
              </a>
            ))}
          </div>
        ))}
      </div>
    </footer>
  );
}
