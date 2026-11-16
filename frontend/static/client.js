"use strict";

(function () {
  const districts = ["Tất cả khu vực", "Hải Châu", "Thanh Khê", "Sơn Trà", "Ngũ Hành Sơn", "Liên Chiểu", "Cẩm Lệ", "Hòa Vang", "Hoàng Sa", "Chưa rõ"];
  const icons = { "Giấy tờ": "🪪", "Ví & túi": "👛", "Điện tử": "📱", "Chìa khóa": "🔑", "Thú cưng": "🐈", "Khác": "📦" };
  const cards = document.getElementById("cards");
  const searchInput = document.getElementById("search-input");
  const categoryFilter = document.getElementById("category-filter");
  const resultCount = document.getElementById("result-count");
  const postModal = document.getElementById("modal");
  const postForm = document.getElementById("report-form");
  const postError = document.getElementById("form-error");
  const reportType = document.getElementById("report-type");
  const reportDistrict = document.getElementById("report-district");
  const reportDistrictLabel = document.querySelector('label[for="report-district"]');
  const reportLocation = document.getElementById("report-location");
  const reportLocationLabel = document.querySelector('label[for="report-location"]');
  const reportLocationHint = document.getElementById("report-location-hint");
  const lostMapPanel = document.getElementById("lost-map-panel");
  const lostMap = document.getElementById("lost-map");
  const verifyModal = document.getElementById("verification-modal");
  const verifyForm = document.getElementById("verification-form");
  const verifyError = document.getElementById("verification-error");
  const verifyInbox = document.getElementById("verification-inbox");
  const meetingFields = document.getElementById("meeting-fields");
  const meetingLocation = document.getElementById("meeting-location");
  const meetingAt = document.getElementById("meeting-at");
  const meetingIsPublic = document.getElementById("meeting-is-public");
  const meetingSafetyWarning = document.getElementById("meeting-safety-warning");
  const authModal = document.getElementById("auth-modal");
  const authForm = document.getElementById("auth-form");
  const authError = document.getElementById("auth-error");
  let csrfToken = "";
  let currentUser = null;
  let posts = [];
  let activeType = "all";
  let activeDistrict = "Tất cả khu vực";
  let authMode = "login";
  let adminTab = "users";
  let toastTimer;

  function escapeHTML(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function updatePrivateClueField() {
    const isFound = reportType.value === "found";
    const clueField = document.getElementById("report-clue-field");
    const clueInput = document.getElementById("report-clue");
    clueField.hidden = false;
    clueInput.required = true;
    clueInput.disabled = false;
    document.querySelector('label[for="report-clue"]').textContent = isFound
      ? "Đặc điểm bí mật chỉ người nhặt biết"
      : "Đặc điểm bí mật để xác minh người tìm thấy";
    document.getElementById("report-clue-hint").textContent = isFound
      ? "Chỉ dùng để đối chiếu chủ món đồ, không hiển thị công khai. Không ghi mã OTP, mật khẩu hay toàn bộ số giấy tờ."
      : "Chỉ dùng để đối chiếu phản hồi, không hiển thị công khai. Không ghi mã OTP, mật khẩu hay toàn bộ số giấy tờ.";
  }

  function updateLocationRequirements() {
    const isLost = reportType.value === "lost";
    reportDistrict.required = !isLost;
    reportLocation.required = !isLost;
    reportDistrictLabel.textContent = isLost ? "Quận / khu vực (nếu biết)" : "Quận / khu vực";
    reportLocationLabel.textContent = isLost
      ? "Đường hoặc khu vực mất đồ"
      : "Đường hoặc khu vực nhặt được";
    reportLocation.placeholder = isLost
      ? "Ví dụ: đường Nguyễn Văn Linh hoặc gần cầu Rồng"
      : "Tên đường hoặc địa điểm nhặt được";
    reportLocationHint.textContent = isLost
      ? "Chỉ cần chọn quận/khu vực hoặc nhập đường/khu vực; có thể điền cả hai để dễ tìm hơn."
      : "Vui lòng cung cấp cả quận/khu vực và địa điểm cụ thể.";
    reportLocation.setCustomValidity(
      isLost && !reportDistrict.value && !reportLocation.value.trim()
        ? "Hãy nhập đường/khu vực mất đồ hoặc chọn quận."
        : ""
    );
  }

  function normalize(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("vi");
  }

  function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("show"); }, 3200);
  }

  async function getCsrf() {
    const response = await fetch("/api/csrf");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Không thể tạo phiên làm việc.");
    csrfToken = data.csrf_token;
    return csrfToken;
  }

  async function api(path, options) {
    const settings = options || {};
    const method = (settings.method || "GET").toUpperCase();
    const headers = new Headers(settings.headers || {});
    if (settings.body && typeof settings.body !== "string") {
      headers.set("Content-Type", "application/json");
      settings.body = JSON.stringify(settings.body);
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      if (!csrfToken) await getCsrf();
      headers.set("X-CSRF-Token", csrfToken);
    }
    const response = await fetch(path, Object.assign({}, settings, { method: method, headers: headers }));
    let data = {};
    try { data = await response.json(); } catch (_error) { /* API errors are shown below. */ }
    if (data.csrf_token) csrfToken = data.csrf_token;
    if (!response.ok) {
      if (response.status === 401) openAuth("login");
      throw new Error(data.error || "Có lỗi xảy ra. Vui lòng thử lại.");
    }
    return data;
  }

  function setAuthMode(mode) {
    authMode = mode;
    const registering = mode === "register";
    document.getElementById("auth-title").textContent = registering ? "Tạo tài khoản" : "Đăng nhập";
    document.getElementById("auth-subtitle").textContent = registering
      ? "Tham gia cộng đồng tìm đồ thất lạc Đà Nẵng."
      : "Đăng nhập để đăng tin và xác minh chủ món đồ.";
    document.getElementById("auth-submit").textContent = registering ? "Tạo tài khoản" : "Đăng nhập";
    document.getElementById("auth-name-field").hidden = !registering;
    document.getElementById("auth-phone-field").hidden = !registering;
    document.getElementById("auth-name").required = registering;
    document.getElementById("auth-phone").required = registering;
    document.getElementById("auth-name").disabled = !registering;
    document.getElementById("auth-phone").disabled = !registering;
    document.querySelectorAll("[data-auth-mode]").forEach(function (button) {
      button.classList.toggle("active", button.dataset.authMode === mode);
    });
    document.getElementById("auth-password").autocomplete = registering ? "new-password" : "current-password";
    authError.classList.remove("show");
  }

  function openAuth(mode) {
    setAuthMode(mode || "login");
    authModal.classList.add("open");
    document.getElementById("auth-email").focus();
  }

  function updateHeader() {
    const area = document.getElementById("account-buttons");
    if (!currentUser) {
      area.innerHTML = '<button type="button" class="secondary-btn" id="open-auth">Đăng nhập</button>' +
        '<button type="button" class="secondary-btn" id="open-register">Tạo tài khoản</button>';
      document.getElementById("open-auth").addEventListener("click", function () { openAuth("login"); });
      document.getElementById("open-register").addEventListener("click", function () { openAuth("register"); });
      return;
    }
    const roleLabel = currentUser.roles.includes("admin") ? "Quản trị viên" : "Người dùng";
    area.innerHTML = '<span class="account-label">' + escapeHTML(currentUser.display_name) + '</span>' +
      '<button class="secondary-btn" type="button" id="my-posts-button">Tin của tôi</button>' +
      '<button class="secondary-btn" type="button" id="my-requests-button">Yêu cầu của tôi</button>' +
      (currentUser.roles.includes("admin") ? '<button class="secondary-btn" type="button" id="admin-button">Quản trị</button>' : "") +
      '<button class="secondary-btn" type="button" id="logout-button">Đăng xuất</button>';
    area.title = roleLabel + " · " + currentUser.email;
    document.getElementById("my-posts-button").addEventListener("click", function () { showView("my-posts"); });
    document.getElementById("my-requests-button").addEventListener("click", function () { showView("my-requests"); });
    const adminButton = document.getElementById("admin-button");
    if (adminButton) adminButton.addEventListener("click", function () { showView("admin"); });
    document.getElementById("logout-button").addEventListener("click", logout);
  }

  function renderDistricts() {
    const root = document.getElementById("district-list");
    root.innerHTML = districts.map(function (district) {
      const count = district === "Tất cả khu vực" ? posts.length
        : posts.filter(function (post) { return post.district === district; }).length;
      return '<button class="district-btn' + (activeDistrict === district ? " selected" : "") +
        '" type="button" data-district="' + escapeHTML(district) + '"><span>' + escapeHTML(district) +
        '</span><span>' + count + '</span></button>';
    }).join("");
  }

  function formatPostLocation(post) {
    const area = post.district === "Chưa rõ" ? "" : post.district;
    const location = post.location === area ? "" : post.location;
    return [area, location].filter(Boolean).join(" · ") || "Chưa rõ khu vực";
  }

  function renderLostMap(query, category) {
    lostMapPanel.hidden = activeType !== "lost";
    if (lostMapPanel.hidden) return;

    const matchingPosts = posts.filter(function (post) {
      const text = normalize([post.title, post.description, post.location, post.district, post.category, post.poster_name].join(" "));
      return post.type === "lost" &&
        (category === "all" || post.category === category) &&
        (!query || text.includes(query));
    });

    lostMapPanel.querySelectorAll("[data-map-district]").forEach(function (button) {
      const district = button.dataset.mapDistrict;
      const count = district === "Tất cả khu vực"
        ? matchingPosts.length
        : matchingPosts.filter(function (post) { return post.district === district; }).length;
      const countLabel = button.querySelector(".map-area-count");
      if (countLabel) countLabel.textContent = count;
      button.classList.toggle("selected", activeDistrict === district);
      button.setAttribute("aria-pressed", String(activeDistrict === district));
      button.setAttribute("aria-label", district + ": " + count + " tin đang tìm");
    });
  }

  function renderPosts() {
    const query = normalize(searchInput.value.trim());
    const category = categoryFilter.value;
    const visible = posts.filter(function (post) {
      const text = normalize([post.title, post.description, post.location, post.district, post.category, post.poster_name].join(" "));
      return (activeType === "all" || post.type === activeType) &&
        (category === "all" || post.category === category) &&
        (activeDistrict === "Tất cả khu vực" || post.district === activeDistrict) &&
        (!query || text.includes(query));
    });
    document.getElementById("total-count").textContent = posts.length;
    document.getElementById("lost-count").textContent = posts.filter(function (post) { return post.type === "lost"; }).length;
    document.getElementById("found-count").textContent = posts.filter(function (post) { return post.type === "found"; }).length;
    resultCount.textContent = "Hiển thị " + visible.length + " tin đăng";
    renderDistricts();
    renderLostMap(query, category);
    if (!visible.length) {
      cards.innerHTML = '<div class="empty"><span>🔎</span>Chưa có tin phù hợp. Hãy thử bộ lọc khác hoặc đăng tin để cộng đồng cùng tìm.</div>';
      return;
    }
    cards.innerHTML = visible.map(function (post) {
      const own = Boolean(post.is_mine);
      const status = post.type === "lost" ? "ĐANG TÌM" : "ĐÃ NHẶT ĐƯỢC";
      const canRespond = !own;
      const verifyLabel = post.type === "found" ? "✦ Tôi là chủ món đồ" : "✦ Tôi đã tìm thấy món đồ này";
      const verify = canRespond && !own
        ? '<button class="contact-btn" type="button" data-verify="' + escapeHTML(post.id) + '">' + verifyLabel + "</button>" : "";
      const inbox = own && Number(post.pending_verifications) > 0
        ? '<button class="contact-btn" type="button" data-review="' + escapeHTML(post.id) + '">📩 Phản hồi mới (' + escapeHTML(post.pending_verifications) + ')</button>' : "";
      const poster = post.poster_name ? '<span>👤 ' + escapeHTML(post.poster_name) + '</span>' : "";
      return '<article class="card"><div class="item-icon" aria-hidden="true">' +
        escapeHTML(icons[post.category] || "📦") + '</div><div class="card-content">' +
        '<div class="card-head"><h3>' + escapeHTML(post.title) + '</h3>' +
        '<span class="badge ' + (post.type === "lost" ? "lost" : "found") + '">' + status + '</span></div>' +
        '<p class="description">' + escapeHTML(post.description) + '</p>' +
        '<div class="card-meta"><span>📍 ' + escapeHTML(formatPostLocation(post)) +
        '</span><span>◷ ' + escapeHTML(formatDate(post.date)) + '</span>' + poster + '</div>' +
        '<div class="card-actions">' + verify + inbox + '</div></div></article>';
    }).join("");
  }

  function formatDate(value) {
    const parts = String(value || "").slice(0, 10).split("-");
    return parts.length === 3 ? parts[2] + "/" + parts[1] + "/" + parts[0] : value;
  }

  function formatMeetingAt(value) {
    const parts = String(value || "").split("T");
    return parts.length === 2 ? formatDate(parts[0]) + " " + parts[1] : value;
  }

  function renderMeetingDetails(item) {
    if (!item.meeting_location || !item.meeting_at) return "";
    const confirmation = item.meeting_is_public
      ? "Người đề xuất xác nhận đây là nơi công cộng, đông người."
      : "Người đề xuất chưa xác nhận đây là nơi công cộng, đông người.";
    const warning = item.meeting_safety_warning
      ? '<div class="safety-warning" role="alert">⚠️ Cảnh báo an toàn: giờ hẹn ngoài 06:00–22:00 và địa điểm chưa được xác nhận là nơi công cộng, đông người. Không nên đi một mình; hãy yêu cầu đổi giờ hoặc địa điểm và báo người thân.</div>'
      : "";
    return '<div class="meeting-details"><strong>Đề xuất hẹn trả đồ</strong><p>📍 ' +
      escapeHTML(item.meeting_location) + '<br>🕒 ' + escapeHTML(formatMeetingAt(item.meeting_at)) +
      '</p><p class="status-text">' + confirmation + "</p>" + warning + "</div>";
  }

  function updateMeetingSafetyWarning() {
    const timePart = meetingAt.value.split("T")[1] || "";
    const hour = Number(timePart.slice(0, 2));
    const minute = Number(timePart.slice(3, 5));
    const outsideRecommendedHours = timePart &&
      (hour < 6 || hour > 22 || (hour === 22 && minute > 0));
    meetingSafetyWarning.hidden = !(outsideRecommendedHours && !meetingIsPublic.checked);
  }

  async function refreshPosts() {
    const data = await api("/api/posts");
    posts = data.posts;
    renderPosts();
  }

  function showView(name) {
    document.getElementById("feed-view").hidden = name !== "feed";
    document.getElementById("admin-panel").hidden = name !== "admin";
    document.getElementById("my-posts-panel").hidden = name !== "my-posts";
    document.getElementById("my-requests-panel").hidden = name !== "my-requests";
    if (name === "admin") loadAdmin();
    if (name === "my-posts") loadMyPosts();
    if (name === "my-requests") loadMyRequests();
  }

  async function loadMyRequests() {
    const container = document.getElementById("my-requests");
    container.innerHTML = '<div class="empty">Đang tải yêu cầu...</div>';
    try {
      const data = await api("/api/my/verifications");
      if (!data.requests.length) {
        container.innerHTML = '<div class="empty"><span>📭</span>Bạn chưa gửi phản hồi nào.</div>';
        return;
      }
      container.innerHTML = data.requests.map(function (item) {
        const status = item.status === "accepted" ? "ĐÃ CHẤP NHẬN"
          : item.status === "rejected" ? "ĐÃ TỪ CHỐI" : "ĐANG CHỜ";
        const contact = item.contact_phone
          ? '<a class="contact-btn" href="tel:' + escapeHTML(item.contact_phone) + '">☎ Liên hệ người đăng</a>'
          : '<span class="status-text">Thông tin liên hệ sẽ hiện sau khi người đăng chấp nhận.</span>';
        return '<article class="card"><div class="item-icon">' + escapeHTML(icons["Khác"]) +
          '</div><div class="card-content"><div class="card-head"><h3>' + escapeHTML(item.post_title) +
          '</h3><span class="badge ' + (item.status === "accepted" ? "found" : "sample") + '">' +
          status + '</span></div><div class="card-meta"><span>📍 ' + escapeHTML(formatPostLocation(item)) +
          '</span><span>' +
          (item.post_type === "found" ? "Yêu cầu nhận đồ" : "Báo đã tìm thấy đồ") +
          "</span></div>" + renderMeetingDetails(item) + contact + "</div></article>";
      }).join("");
    } catch (error) {
      container.innerHTML = '<div class="empty">' + escapeHTML(error.message) + "</div>";
    }
  }

  async function loadMyPosts() {
    const container = document.getElementById("my-posts");
    container.innerHTML = '<div class="empty">Đang tải tin đăng...</div>';
    try {
      const data = await api("/api/my/posts");
      if (!data.posts.length) {
        container.innerHTML = '<div class="empty"><span>📭</span>Bạn chưa có tin đăng nào.</div>';
        return;
      }
      container.innerHTML = data.posts.map(function (post) {
        const nextStatus = post.status === "open" ? "resolved" : "open";
        const buttonText = post.status === "open" ? "Đánh dấu đã xử lý" : "Mở lại tin";
        return '<article class="card"><div class="item-icon">' + escapeHTML(icons[post.category] || "📦") +
          '</div><div class="card-content"><div class="card-head"><h3>' + escapeHTML(post.title) +
          '</h3><span class="badge ' + (post.status === "open" ? "found" : "sample") + '">' +
          escapeHTML(post.status === "open" ? "ĐANG HIỂN THỊ" : post.status === "resolved" ? "ĐÃ XỬ LÝ" : "ĐÃ ẨN") +
          '</span></div><p class="description">' + escapeHTML(post.description) + '</p><div class="card-meta"><span>📍 ' +
          escapeHTML(formatPostLocation(post)) + '</span><span class="status-text">Yêu cầu xác minh: ' +
          escapeHTML(post.verification_count) + '</span></div>' +
          (post.status !== "hidden" ? '<button class="contact-btn" type="button" data-my-status="' +
            escapeHTML(post.id) + '" data-status="' + nextStatus + '">' + buttonText + '</button>' : "") +
          '</div></article>';
      }).join("");
    } catch (error) {
      container.innerHTML = '<div class="empty">' + escapeHTML(error.message) + '</div>';
    }
  }

  function adminTable(headers, rows) {
    return '<table class="admin-table"><thead><tr>' + headers.map(function (header) {
      return "<th>" + escapeHTML(header) + "</th>";
    }).join("") + '</tr></thead><tbody>' + (rows || []).join("") + "</tbody></table>";
  }

  async function loadAdmin() {
    if (!currentUser || !currentUser.roles.includes("admin")) return;
    try {
      const overview = await api("/api/admin/overview");
      document.getElementById("admin-stats").innerHTML = [
        ["Tài khoản", overview.overview.users],
        ["Tổng tin đăng", overview.overview.posts],
        ["Tin đang mở", overview.overview.open_posts],
        ["Chờ xác minh", overview.overview.pending_verifications]
      ].map(function (item) {
        return '<div class="admin-stat"><strong>' + escapeHTML(item[1]) + "</strong>" + item[0] + "</div>";
      }).join("");
      await renderAdminTab();
    } catch (error) {
      document.getElementById("admin-content").textContent = error.message;
    }
  }

  async function renderAdminTab() {
    const container = document.getElementById("admin-content");
    container.innerHTML = '<p class="inbox-empty">Đang tải...</p>';
    try {
      if (adminTab === "users") {
        const data = await api("/api/admin/users");
        container.innerHTML = adminTable(["Tài khoản", "Email", "Vai trò", "Điện thoại", "Trạng thái", "Thao tác"],
          data.users.map(function (user) {
            const isCurrentUser = Number(user.id) === Number(currentUser.id);
            return "<tr><td>" + escapeHTML(user.display_name) + "</td><td>" + escapeHTML(user.email) +
              "</td><td>" + escapeHTML(user.roles.join(", ")) + "</td><td>" + escapeHTML(user.phone) +
              '</td><td>' + (user.is_active ? "Đang hoạt động" : "Đã khóa") +
              '</td><td><button class="table-action ' + (user.is_active ? "danger-btn" : "accept-btn") +
              '" data-user-id="' + escapeHTML(user.id) + '" data-active="' + (user.is_active ? "false" : "true") +
              '"' + (isCurrentUser ? " disabled" : "") + ">" +
              (isCurrentUser ? "Đang đăng nhập" : user.is_active ? "Khóa" : "Mở khóa") + "</button></td></tr>";
          }));
      } else if (adminTab === "posts") {
        const data = await api("/api/admin/posts");
        container.innerHTML = adminTable(["Tin đăng", "Loại", "Người đăng", "Khu vực", "Trạng thái", "Thao tác"],
          data.posts.map(function (post) {
            const nextStatus = post.status === "hidden" ? "open" : "hidden";
            return "<tr><td>" + escapeHTML(post.title) + "<br>" + escapeHTML(post.description) +
              "</td><td>" + escapeHTML(post.type) + "</td><td>" + escapeHTML(post.poster_email) +
              "</td><td>" + escapeHTML(post.district) + "</td><td>" + escapeHTML(post.status) +
              '</td><td><button class="table-action ' + (post.status === "hidden" ? "accept-btn" : "danger-btn") +
              '" data-post-id="' + escapeHTML(post.id) + '" data-post-status="' + nextStatus + '">' +
              (post.status === "hidden" ? "Hiện tin" : "Ẩn tin") + "</button></td></tr>";
          }));
      } else {
        const data = await api("/api/admin/verifications");
        container.innerHTML = adminTable(["Tin đăng", "Người gửi", "Thông tin đối chiếu", "AI", "Lý do cảnh báo", "Liên hệ", "Trạng thái", "Thao tác"],
          data.requests.map(function (item) {
            const controls = item.status === "pending"
              ? '<button class="table-action accept-btn" data-admin-verification="' + escapeHTML(item.id) +
                '" data-verification-status="accepted">Chấp nhận</button><button class="table-action danger-btn" data-admin-verification="' +
                escapeHTML(item.id) + '" data-verification-status="rejected">Từ chối</button>' : "";
            return "<tr><td>" + escapeHTML(item.post_title) + "</td><td>" + escapeHTML(item.claimant_email) +
              "</td><td>" + escapeHTML(item.details) + '</td><td><span class="risk-badge ' +
              escapeHTML(item.risk_level) + '">' + escapeHTML(item.risk_score) + "/100 · " +
              escapeHTML(item.risk_level) + "</span></td><td>" +
              escapeHTML((item.risk_reasons || []).join(" ")) + "</td><td>" + escapeHTML(item.contact_phone) +
              "</td><td>" + escapeHTML(item.status) + "</td><td>" + controls + "</td></tr>";
          }));
      }
    } catch (error) {
      container.innerHTML = '<p class="inbox-empty">' + escapeHTML(error.message) + "</p>";
    }
  }

  function openPostForm() {
    if (!currentUser) {
      openAuth("login");
      showToast("Đăng nhập hoặc tạo tài khoản để đăng tin.");
      return;
    }
    const typeSelect = document.getElementById("report-type");
    typeSelect.querySelector('[value="lost"]').disabled = false;
    typeSelect.querySelector('[value="found"]').disabled = false;
    typeSelect.value = "lost";
    updatePrivateClueField();
    updateLocationRequirements();
    postModal.classList.add("open");
    document.getElementById("report-date").value = new Date().toISOString().slice(0, 10);
    document.getElementById("report-title").focus();
  }

  function closeVerification() {
    verifyModal.classList.remove("open");
    verifyError.classList.remove("show");
  }

  async function openVerification(postId, showInbox) {
    const post = posts.find(function (item) { return item.id === postId; });
    if (!post) return;
    if (!currentUser) {
      openAuth("login");
      showToast("Đăng nhập để gửi hoặc xem phản hồi.");
      return;
    }
    verifyForm.reset();
    document.getElementById("verification-item").textContent = post.title + " · " + post.district;
    const foundPost = post.type === "found";
    meetingFields.hidden = foundPost;
    meetingLocation.required = !foundPost;
    meetingAt.required = !foundPost;
    meetingAt.min = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    updateMeetingSafetyWarning();
    document.getElementById("verification-title").textContent = foundPost
      ? "Xác minh chủ món đồ" : "Phản hồi tin mất đồ";
    document.getElementById("verification-details-label").textContent = foundPost
      ? "Chi tiết riêng chứng minh bạn là chủ món đồ"
      : "Đặc điểm món đồ bạn đã tìm thấy";
    document.getElementById("verification-details").placeholder = foundPost
      ? "Nêu đặc điểm kín của món đồ mà người nhặt chưa công bố..."
      : "Mô tả chi tiết món đồ bạn đã tìm thấy để chủ tin xác nhận...";
    document.getElementById("verification-submit").textContent = foundPost
      ? "Gửi yêu cầu xác minh" : "Gửi phản hồi tìm thấy";
    document.getElementById("verification-post-id").value = postId;
    verifyError.classList.remove("show");
    verifyForm.hidden = showInbox;
    verifyInbox.hidden = !showInbox;
    verifyInbox.innerHTML = "";
    verifyModal.classList.add("open");
    if (!showInbox) {
      document.getElementById("verification-details").focus();
      return;
    }
    try {
      const data = await api("/api/posts/" + encodeURIComponent(postId) + "/verifications");
      verifyInbox.innerHTML = '<h3 class="inbox-title">' +
        (foundPost ? "Người nhận là chủ món đồ" : "Người đã tìm thấy món đồ") + "</h3>" +
        (data.requests.length ? '<div class="request-list">' + data.requests.map(function (item) {
          const actions = item.status === "pending"
            ? '<div class="request-actions"><button class="accept-btn" type="button" data-review-id="' +
              escapeHTML(item.id) + '" data-review-status="accepted">Chấp nhận phản hồi</button>' +
              '<button class="reject-btn" type="button" data-review-id="' + escapeHTML(item.id) +
              '" data-review-status="rejected">Từ chối</button></div>' : "";
          const contact = item.contact_phone
            ? '<a href="tel:' + escapeHTML(item.contact_phone) + '">☎ ' + escapeHTML(item.contact_phone) + "</a>"
            : '<p class="status-text">Số điện thoại sẽ được chia sẻ sau khi chấp nhận.</p>';
          return '<article class="request-card"><strong>' + escapeHTML(item.claimant_name) +
            '</strong> <span class="risk-badge ' + escapeHTML(item.risk_level) + '">AI: ' +
            escapeHTML(item.risk_level === "high" ? "Rủi ro cao" : item.risk_level === "medium" ? "Cần xem xét" : "Rủi ro thấp") +
            " · " + escapeHTML(item.risk_score) + "/100</span><p>" + escapeHTML(item.details) + '</p><p class="status-text">' +
            escapeHTML((item.risk_reasons || []).join(" ")) + "</p>" + renderMeetingDetails(item) + contact +
            '<p class="status-text">Trạng thái: ' + escapeHTML(item.status) + "</p>" + actions + "</article>";
        }).join("") + "</div>" : '<p class="inbox-empty">Chưa có yêu cầu xác minh.</p>');
    } catch (error) {
      verifyInbox.innerHTML = '<p class="inbox-empty">' + escapeHTML(error.message) + "</p>";
    }
  }

  async function logout() {
    try {
      await api("/api/logout", { method: "POST" });
      currentUser = null;
      csrfToken = "";
      updateHeader();
      showView("feed");
      await refreshPosts();
      showToast("Đã đăng xuất.");
    } catch (error) {
      showToast(error.message);
    }
  }

  document.getElementById("open-report").addEventListener("click", openPostForm);
  reportType.addEventListener("change", function () {
    updatePrivateClueField();
    updateLocationRequirements();
  });
  reportDistrict.addEventListener("change", updateLocationRequirements);
  reportLocation.addEventListener("input", updateLocationRequirements);
  document.getElementById("close-modal").addEventListener("click", function () { postModal.classList.remove("open"); });
  document.getElementById("cancel-modal").addEventListener("click", function () { postModal.classList.remove("open"); });
  postModal.addEventListener("click", function (event) { if (event.target === postModal) postModal.classList.remove("open"); });
  document.getElementById("close-auth").addEventListener("click", function () { authModal.classList.remove("open"); });
  authModal.addEventListener("click", function (event) { if (event.target === authModal) authModal.classList.remove("open"); });
  document.getElementById("close-verification").addEventListener("click", closeVerification);
  verifyModal.addEventListener("click", function (event) { if (event.target === verifyModal) closeVerification(); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      postModal.classList.remove("open");
      authModal.classList.remove("open");
      closeVerification();
    }
  });
  document.querySelectorAll("[data-auth-mode]").forEach(function (button) {
    button.addEventListener("click", function () { setAuthMode(button.dataset.authMode); });
  });
  document.querySelectorAll("[data-view]").forEach(function (button) {
    button.addEventListener("click", function () { showView(button.dataset.view); });
  });
  document.querySelectorAll(".chip[data-type]").forEach(function (button) {
    button.addEventListener("click", function () {
      activeType = button.dataset.type;
      document.querySelectorAll(".chip[data-type]").forEach(function (chip) {
        chip.classList.toggle("active", chip === button);
      });
      renderPosts();
    });
  });
  document.getElementById("district-list").addEventListener("click", function (event) {
    const button = event.target.closest("[data-district]");
    if (!button) return;
    activeDistrict = button.dataset.district;
    renderPosts();
  });
  lostMapPanel.addEventListener("click", function (event) {
    const button = event.target.closest("[data-map-district]");
    if (!button) return;
    activeDistrict = button.dataset.mapDistrict;
    renderPosts();
  });
  searchInput.addEventListener("input", renderPosts);
  categoryFilter.addEventListener("change", renderPosts);

  authForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!authForm.reportValidity()) return;
    authError.classList.remove("show");
    const data = {
      email: document.getElementById("auth-email").value.trim(),
      password: document.getElementById("auth-password").value
    };
    if (authMode === "register") {
      data.display_name = document.getElementById("auth-name").value.trim();
      data.phone = document.getElementById("auth-phone").value.trim();
    }
    try {
      const result = await api(authMode === "register" ? "/api/register" : "/api/login", {
        method: "POST", body: data
      });
      currentUser = result.user;
      authModal.classList.remove("open");
      authForm.reset();
      updateHeader();
      await refreshPosts();
      showToast("Xin chào, " + currentUser.display_name + "!");
    } catch (error) {
      authError.textContent = error.message;
      authError.classList.add("show");
    }
  });

  postForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    updateLocationRequirements();
    if (!postForm.reportValidity()) return;
    postError.classList.remove("show");
    const data = {
      type: document.getElementById("report-type").value,
      category: document.getElementById("report-category").value,
      title: document.getElementById("report-title").value.trim(),
      description: document.getElementById("report-description").value.trim(),
      district: document.getElementById("report-district").value,
      location: document.getElementById("report-location").value.trim(),
      date: document.getElementById("report-date").value,
      phone: document.getElementById("report-phone").value.trim()
    };
    data.private_clue = document.getElementById("report-clue").value.trim();
    try {
      await api("/api/posts", { method: "POST", body: data });
      postForm.reset();
      postModal.classList.remove("open");
      activeType = "all";
      activeDistrict = "Tất cả khu vực";
      searchInput.value = "";
      categoryFilter.value = "all";
      document.querySelector('.chip[data-type="all"]').click();
      await refreshPosts();
      showView("feed");
      showToast("Đăng tin thành công.");
    } catch (error) {
      postError.textContent = error.message;
      postError.classList.add("show");
    }
  });

  verifyForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!verifyForm.reportValidity()) return;
    verifyError.classList.remove("show");
    const postId = document.getElementById("verification-post-id").value;
    try {
      await api("/api/posts/" + encodeURIComponent(postId) + "/verifications", {
        method: "POST",
        body: Object.assign({
          details: document.getElementById("verification-details").value.trim(),
          phone: document.getElementById("verification-phone").value.trim()
        }, meetingFields.hidden ? {} : {
          meeting_location: meetingLocation.value.trim(),
          meeting_at: meetingAt.value,
          meeting_is_public: meetingIsPublic.checked
        })
      });
      verifyForm.reset();
      closeVerification();
      await refreshPosts();
      const post = posts.find(function (item) { return item.id === postId; });
      showToast(post && post.type === "lost"
        ? "Đã gửi thông tin cho người đăng tin."
        : "Đã gửi thông tin để người nhặt đối chiếu.");
    } catch (error) {
      verifyError.textContent = error.message;
      verifyError.classList.add("show");
    }
  });

  cards.addEventListener("click", function (event) {
    const verify = event.target.closest("[data-verify]");
    const review = event.target.closest("[data-review]");
    if (verify) openVerification(verify.dataset.verify, false);
    if (review) openVerification(review.dataset.review, true);
  });

  verifyInbox.addEventListener("click", async function (event) {
    const button = event.target.closest("[data-review-id]");
    if (!button) return;
    try {
      await api("/api/verifications/" + encodeURIComponent(button.dataset.reviewId), {
        method: "PATCH", body: { status: button.dataset.reviewStatus }
      });
      closeVerification();
      await refreshPosts();
      showToast(button.dataset.reviewStatus === "accepted" ? "Đã chấp nhận phản hồi." : "Đã từ chối yêu cầu.");
    } catch (error) {
      verifyError.textContent = error.message;
      verifyError.classList.add("show");
    }
  });
  meetingAt.addEventListener("input", updateMeetingSafetyWarning);
  meetingIsPublic.addEventListener("change", updateMeetingSafetyWarning);

  document.getElementById("my-posts").addEventListener("click", async function (event) {
    const button = event.target.closest("[data-my-status]");
    if (!button) return;
    try {
      await api("/api/posts/" + encodeURIComponent(button.dataset.myStatus), {
        method: "PATCH", body: { status: button.dataset.status }
      });
      await loadMyPosts();
      await refreshPosts();
      showToast("Đã cập nhật trạng thái tin đăng.");
    } catch (error) {
      showToast(error.message);
    }
  });

  document.querySelectorAll("[data-admin-tab]").forEach(function (button) {
    button.addEventListener("click", function () {
      adminTab = button.dataset.adminTab;
      document.querySelectorAll("[data-admin-tab]").forEach(function (tab) {
        tab.classList.toggle("active", tab === button);
      });
      renderAdminTab();
    });
  });
  document.getElementById("admin-content").addEventListener("click", async function (event) {
    const userButton = event.target.closest("[data-user-id]");
    const postButton = event.target.closest("[data-post-id]");
    const verificationButton = event.target.closest("[data-admin-verification]");
    try {
      if (userButton) {
        await api("/api/admin/users/" + userButton.dataset.userId, {
          method: "PATCH", body: { is_active: userButton.dataset.active === "true" }
        });
        showToast("Đã cập nhật tài khoản.");
      } else if (postButton) {
        await api("/api/admin/posts/" + encodeURIComponent(postButton.dataset.postId), {
          method: "PATCH", body: { status: postButton.dataset.postStatus }
        });
        await refreshPosts();
        showToast("Đã cập nhật tin đăng.");
      } else if (verificationButton) {
        await api("/api/admin/verifications/" + encodeURIComponent(verificationButton.dataset.adminVerification), {
          method: "PATCH", body: { status: verificationButton.dataset.verificationStatus }
        });
        showToast("Đã xử lý yêu cầu xác minh.");
      } else {
        return;
      }
      await loadAdmin();
    } catch (error) {
      showToast(error.message);
    }
  });

  async function initialize() {
    try {
      await getCsrf();
      const data = await api("/api/me");
      currentUser = data.user;
      updateHeader();
      await refreshPosts();
    } catch (error) {
      resultCount.textContent = error.message;
      cards.innerHTML = '<div class="empty"><span>⚠️</span>Không thể kết nối máy chủ ứng dụng.</div>';
    }
  }

  setAuthMode("login");
  updateHeader();
  initialize();
}());
