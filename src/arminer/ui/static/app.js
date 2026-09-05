// arminer Web Studio — Enterprise Client Logic with Industry Taxonomy
document.addEventListener('DOMContentLoaded', () => {
  // State
  let currentReports = [];
  let selectedReports = new Map(); // record_id -> report object
  let currentDictData = null;
  let activeCategoryFilter = 'all';
  let sectorsHierarchy = [];

  // --------------------------------------------------------------------------
  // 1. Tab Navigation
  // --------------------------------------------------------------------------
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');

  function switchTab(tabId) {
    tabBtns.forEach(b => {
      if (b.getAttribute('data-tab') === tabId) b.classList.add('active');
      else b.classList.remove('active');
    });

    tabPanels.forEach(p => {
      if (p.id === tabId) p.classList.add('active');
      else p.classList.remove('active');
    });
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab');
      switchTab(targetId);
    });
  });

  // --------------------------------------------------------------------------
  // 2. Catalog & Mining Tab with Industry Taxonomy
  // --------------------------------------------------------------------------
  const catTickerInput = document.getElementById('catTickerInput');
  const catSectorL1 = document.getElementById('catSectorL1');
  const catSectorL2 = document.getElementById('catSectorL2');
  const catYearFrom = document.getElementById('catYearFrom');
  const catYearTo = document.getElementById('catYearTo');
  const catLimitSelect = document.getElementById('catLimitSelect');
  const btnSearchCatalog = document.getElementById('btnSearchCatalog');
  const catalogTableBody = document.getElementById('catalogTableBody');
  const chkSelectAll = document.getElementById('chkSelectAll');
  const selectedCountLabel = document.getElementById('selectedCountLabel');
  const btnExecuteSelectedScan = document.getElementById('btnExecuteSelectedScan');
  const catTopicSelect = document.getElementById('catTopicSelect');
  const btnQuickSelect20 = document.getElementById('btnQuickSelect20');
  const btnSelectAllVisible = document.getElementById('btnSelectAllVisible');
  const btnSelectAllMatched = document.getElementById('btnSelectAllMatched');
  const btnClearSelection = document.getElementById('btnClearSelection');

  async function loadSectors() {
    try {
      const res = await fetch('/api/catalog/sectors');
      const data = await res.json();
      sectorsHierarchy = data.sectors || [];

      catSectorL1.innerHTML = '<option value="">Tất cả ngành (L1)</option>';
      sectorsHierarchy.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.name;
        const countStr = (s.report_count || s.local_report_count || 0).toLocaleString();
        opt.textContent = `${s.name} (${s.total_tickers} mã | ${countStr} báo cáo)`;
        catSectorL1.appendChild(opt);
      });
    } catch (err) {
      console.error('Lỗi tải danh mục ngành:', err);
    }
  }

  if (catSectorL1) {
    catSectorL1.addEventListener('change', () => {
      const selectedL1 = catSectorL1.value;
      catSectorL2.innerHTML = '<option value="">Tất cả phân ngành (L2)</option>';

      if (selectedL1) {
        const found = sectorsHierarchy.find(s => s.name === selectedL1);
        if (found && found.subsectors) {
          found.subsectors.forEach(sub => {
            const opt = document.createElement('option');
            opt.value = sub.name;
            const countStr = (sub.report_count || sub.local_report_count || 0).toLocaleString();
            opt.textContent = `${sub.name} (${sub.ticker_count} mã | ${countStr} báo cáo)`;
            catSectorL2.appendChild(opt);
          });
        }
      }
      loadCatalog();
    });
  }

  if (catSectorL2) {
    catSectorL2.addEventListener('change', loadCatalog);
  }

  if (catLimitSelect) {
    catLimitSelect.addEventListener('change', loadCatalog);
  }

  async function loadCatalog() {
    catalogTableBody.innerHTML = `
      <tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">
        <span class="spinner-sm" style="display: inline-block; vertical-align: middle; margin-right: 8px;"></span>
        Đang tải báo cáo từ kho Zenodo...
      </td></tr>
    `;

    const ticker = catTickerInput.value.trim();
    const l1 = catSectorL1 ? catSectorL1.value : '';
    const l2 = catSectorL2 ? catSectorL2.value : '';
    const yFrom = catYearFrom.value;
    const yTo = catYearTo.value;
    const limit = catLimitSelect ? catLimitSelect.value : '500';

    const params = new URLSearchParams();
    if (ticker) params.append('ticker', ticker);
    if (l1) params.append('icb_l1', l1);
    if (l2) params.append('icb_l2', l2);
    if (yFrom) params.append('year_from', yFrom);
    if (yTo) params.append('year_to', yTo);
    params.append('limit', limit);

    try {
      const res = await fetch(`/api/catalog/search?${params.toString()}`);
      const data = await res.json();
      currentReports = data.reports || [];
      renderCatalogTable(data.total_matched);
    } catch (err) {
      catalogTableBody.innerHTML = `
        <tr><td colspan="7" style="text-align: center; color: var(--color-danger); padding: 20px;">
          Lỗi tải dữ liệu: ${err.message}
        </td></tr>
      `;
    }
  }

  function renderCatalogTable(totalMatched) {
    if (currentReports.length === 0) {
      catalogTableBody.innerHTML = `
        <tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 40px;">
          Không tìm thấy báo cáo nào khớp với tiêu chí tìm kiếm.
        </td></tr>
      `;
      const summaryEl = document.getElementById('catalogResultSummary');
      if (summaryEl) summaryEl.innerHTML = 'Hiển thị: <strong>0</strong> báo cáo';
      return;
    }

    catalogTableBody.innerHTML = '';
    currentReports.forEach(r => {
      const tr = document.createElement('tr');
      const isChecked = selectedReports.has(r.record_id);

      tr.innerHTML = `
        <td style="text-align: center;">
          <input type="checkbox" class="custom-chk row-chk" data-id="${r.record_id}" ${isChecked ? 'checked' : ''}>
        </td>
        <td><strong style="color: var(--text-primary); font-family: var(--font-mono);">${r.ticker}</strong></td>
        <td class="tabular">${r.year}</td>
        <td>
          <span class="badge badge-cat" style="margin-bottom: 2px;">${escapeHtml(r.icb_l1 || 'Chưa phân loại')}</span>
          ${r.icb_l2 ? `<div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(r.icb_l2)}</div>` : ''}
        </td>
        <td style="max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(r.file_name)}">
          ${escapeHtml(r.file_name)}
        </td>
        <td style="text-align: center;">
          <span class="badge" style="background: rgba(99,102,241,0.1); color: var(--brand-primary); font-size: 11px;">
            ${r.archive_period || 'Zenodo'}
          </span>
        </td>
        <td style="text-align: right;" class="tabular">${r.file_size_mb ? r.file_size_mb + ' MB' : '—'}</td>
      `;

      const chk = tr.querySelector('.row-chk');
      if (chk) {
        chk.addEventListener('change', (e) => {
          if (e.target.checked) {
            selectedReports.set(r.record_id, r);
          } else {
            selectedReports.delete(r.record_id);
          }
          updateSelectionState();
        });
      }

      catalogTableBody.appendChild(tr);
    });

    updateSelectionState();

    const summaryEl = document.getElementById('catalogResultSummary');
    if (summaryEl) {
      const totalStr = (totalMatched !== undefined ? totalMatched : currentReports.length).toLocaleString();
      summaryEl.innerHTML = `Hiển thị: <strong>${currentReports.length}</strong> / <strong>${totalStr}</strong> báo cáo trong Zenodo`;
    }
  }

  function updateSelectionState() {
    const count = selectedReports.size;

    if (count === 0) {
      selectedCountLabel.textContent = 'Đã chọn: 0 báo cáo';
    } else {
      selectedCountLabel.innerHTML = `Đã chọn: <strong>${count.toLocaleString()}</strong> báo cáo Zenodo`;
    }

    btnExecuteSelectedScan.disabled = count === 0;
    const btnZip = document.getElementById('btnDownloadSelectedZip');
    if (btnZip) btnZip.disabled = count === 0;

    if (currentReports.length > 0 && currentReports.every(r => selectedReports.has(r.record_id))) {
      chkSelectAll.checked = true;
      chkSelectAll.indeterminate = false;
    } else if (count > 0) {
      chkSelectAll.checked = false;
      chkSelectAll.indeterminate = true;
    } else {
      chkSelectAll.checked = false;
      chkSelectAll.indeterminate = false;
    }
  }

  if (chkSelectAll) {
    chkSelectAll.addEventListener('change', (e) => {
      const checked = e.target.checked;
      currentReports.forEach(r => {
        if (checked) selectedReports.set(r.record_id, r);
        else selectedReports.delete(r.record_id);
      });
      renderCatalogTable();
    });
  }

  // Quick action: Select first 20 reports
  if (btnQuickSelect20) {
    btnQuickSelect20.addEventListener('click', () => {
      selectedReports.clear();
      const first20 = currentReports.slice(0, 20);
      first20.forEach(r => selectedReports.set(r.record_id, r));
      renderCatalogTable();
    });
  }

  // Quick action: Select all visible in table
  if (btnSelectAllVisible) {
    btnSelectAllVisible.addEventListener('click', () => {
      currentReports.forEach(r => selectedReports.set(r.record_id, r));
      renderCatalogTable();
    });
  }

  // Quick action: Select ALL matched reports in Zenodo (even if > displayed limit)
  if (btnSelectAllMatched) {
    btnSelectAllMatched.addEventListener('click', async () => {
      btnSelectAllMatched.disabled = true;
      const originalText = btnSelectAllMatched.textContent;
      btnSelectAllMatched.textContent = 'Đang lấy toàn bộ ID...';

      const ticker = catTickerInput.value.trim();
      const l1 = catSectorL1 ? catSectorL1.value : '';
      const l2 = catSectorL2 ? catSectorL2.value : '';
      const yFrom = catYearFrom.value;
      const yTo = catYearTo.value;

      const params = new URLSearchParams();
      if (ticker) params.append('ticker', ticker);
      if (l1) params.append('icb_l1', l1);
      if (l2) params.append('icb_l2', l2);
      if (yFrom) params.append('year_from', yFrom);
      if (yTo) params.append('year_to', yTo);

      try {
        const res = await fetch(`/api/catalog/matched-ids?${params.toString()}`);
        const data = await res.json();
        const ids = data.record_ids || [];

        selectedReports.clear();
        ids.forEach(id => {
          selectedReports.set(id, { record_id: id });
        });

        renderCatalogTable(data.total_matched);
        alert(`Đã chọn toàn bộ ${ids.length.toLocaleString()} báo cáo khớp bộ lọc! Bạn có thể bấm "Khai Phá Báo Cáo Đã Chọn" để bắt đầu quét.`);
      } catch (err) {
        alert('Lỗi: ' + err.message);
      } finally {
        btnSelectAllMatched.disabled = false;
        btnSelectAllMatched.textContent = originalText;
      }
    });
  }

  // Quick action: Clear all selections
  if (btnClearSelection) {
    btnClearSelection.addEventListener('click', () => {
      selectedReports.clear();
      renderCatalogTable();
    });
  }

  if (btnSearchCatalog) {
    btnSearchCatalog.addEventListener('click', loadCatalog);
  }

  // Scan Selected Execution — SSE streaming with progress bar
  if (btnExecuteSelectedScan) {
    btnExecuteSelectedScan.addEventListener('click', async () => {
      const recordIds = Array.from(selectedReports.keys());
      if (recordIds.length === 0) {
        alert('Vui lòng chọn ít nhất một báo cáo để khai phá.');
        return;
      }

      const totalSelected = recordIds.length;
      const topic = catTopicSelect ? catTopicSelect.value : 'blockchain';
      btnExecuteSelectedScan.disabled = true;
      const originalText = document.getElementById('btnScanText').textContent;
      document.getElementById('btnScanText').textContent = `Đang khai phá ${totalSelected} báo cáo...`;

      // Show progress bar
      const progressContainer = document.getElementById('miningProgressContainer');
      const progressBar = document.getElementById('miningProgressBar');
      const progressPct = document.getElementById('miningProgressPct');
      const progressPhase = document.getElementById('miningProgressPhase');
      const progressMsg = document.getElementById('miningProgressMsg');
      const progressCount = document.getElementById('miningProgressCount');

      progressContainer.style.display = 'block';
      progressBar.style.width = '0%';
      progressPct.textContent = '0%';
      progressPhase.textContent = 'Đang chuẩn bị...';
      progressMsg.textContent = 'Đang khởi tạo kết nối...';
      progressCount.textContent = '';

      const body = JSON.stringify({
        record_ids: recordIds,
        topic: topic,
        threshold: 85,
      });

      try {
        const response = await fetch('/api/scan-selected-stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: body,
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || `Lỗi HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalData = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data:')) {
              const jsonStr = line.slice(5).trim();
              if (!jsonStr) continue;

              try {
                const eventData = JSON.parse(jsonStr);

                // Detect event type from the raw SSE
                if (eventData.total_files !== undefined) {
                  // This is the "complete" event
                  finalData = eventData;
                } else if (eventData.detail) {
                  // Error event
                  throw new Error(eventData.detail);
                } else if (eventData.phase) {
                  // Progress event
                  const pct = eventData.total > 0
                    ? Math.round((eventData.current / eventData.total) * 100)
                    : 0;

                  const phaseLabels = {
                    download: 'Tải báo cáo từ Zenodo',
                    mining: 'Khai phá từ khóa',
                    export: 'Tạo file kết quả nghiên cứu',
                  };

                  progressBar.style.width = pct + '%';
                  progressPct.textContent = pct + '%';
                  progressPhase.textContent = phaseLabels[eventData.phase] || eventData.phase;
                  progressMsg.textContent = eventData.message || '';
                  progressCount.textContent = `${eventData.current}/${eventData.total}`;
                }
              } catch (parseErr) {
                if (parseErr.message && !parseErr.message.includes('JSON')) throw parseErr;
              }
            } else if (line.startsWith('event:')) {
              // Track event type for next data line
              // handled inline above
            }
          }
        }

        if (finalData) {
          // Animate to 100%
          progressBar.style.width = '100%';
          progressPct.textContent = '100%';
          progressPhase.textContent = 'Hoàn tất!';
          progressMsg.textContent = `Đã khai phá ${finalData.total_files} báo cáo, tìm thấy ${finalData.total_mentions} từ khóa`;
          progressCount.textContent = '';

          setTimeout(() => {
            renderResearchResults(finalData);
            switchTab('tab-results');
            progressContainer.style.display = 'none';
          }, 1200);
        } else {
          throw new Error('Không nhận được kết quả từ server.');
        }
      } catch (err) {
        progressContainer.style.display = 'none';
        alert(`Lỗi khai phá: ${err.message}`);
      } finally {
        btnExecuteSelectedScan.disabled = false;
        document.getElementById('btnScanText').textContent = originalText;
      }
    });
  }

  // Download Selected Reports as ZIP archive
  const btnDownloadSelectedZip = document.getElementById('btnDownloadSelectedZip');
  if (btnDownloadSelectedZip) {
    btnDownloadSelectedZip.addEventListener('click', async () => {
      const recordIds = Array.from(selectedReports.keys());
      if (recordIds.length === 0) {
        alert('Vui lòng chọn ít nhất một báo cáo để tải về.');
        return;
      }

      const totalSelected = recordIds.length;
      const structureEl = document.getElementById('catZipStructure');
      const structure = structureEl ? structureEl.value : 'ticker';

      btnDownloadSelectedZip.disabled = true;
      const btnText = document.getElementById('btnZipText');
      const originalText = btnText ? btnText.textContent : 'Tải Về File Gốc (.zip)';
      if (btnText) btnText.textContent = `Đang xử lý ${totalSelected} file...`;

      // Show progress bar
      const progressContainer = document.getElementById('miningProgressContainer');
      const progressBar = document.getElementById('miningProgressBar');
      const progressPct = document.getElementById('miningProgressPct');
      const progressPhase = document.getElementById('miningProgressPhase');
      const progressMsg = document.getElementById('miningProgressMsg');
      const progressCount = document.getElementById('miningProgressCount');

      progressContainer.style.display = 'block';
      progressBar.style.width = '0%';
      progressPct.textContent = '0%';
      progressPhase.textContent = 'Chuẩn bị file gốc...';
      progressMsg.textContent = 'Đang khởi tạo kết nối kho lưu trữ...';
      progressCount.textContent = '';

      try {
        const response = await fetch('/api/catalog/download-zip-stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            record_ids: recordIds,
            structure: structure,
            cleanup_cache: document.getElementById('chkZipCleanupCache') ? document.getElementById('chkZipCleanupCache').checked : false,
          }),
        });

        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.detail || `Lỗi máy chủ (${response.status})`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalData = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data:')) {
              const jsonStr = line.slice(5).trim();
              if (!jsonStr) continue;
              try {
                const eventData = JSON.parse(jsonStr);
                if (eventData.download_url) {
                  finalData = eventData;
                } else if (eventData.detail) {
                  throw new Error(eventData.detail);
                } else if (eventData.phase) {
                  const pct = eventData.total > 0
                    ? Math.round((eventData.current / eventData.total) * 100)
                    : 0;

                  const phaseLabels = {
                    prepare: 'Kiểm tra danh mục',
                    download: 'Tải file gốc từ Zenodo',
                    zip: 'Đóng gói & Nén ZIP',
                  };

                  progressBar.style.width = pct + '%';
                  progressPct.textContent = pct + '%';
                  progressPhase.textContent = phaseLabels[eventData.phase] || eventData.phase;
                  progressMsg.textContent = eventData.message || '';
                  if (eventData.total > 0) {
                    progressCount.textContent = `${eventData.current}/${eventData.total}`;
                  }
                }
              } catch (parseErr) {
                if (parseErr.message && !parseErr.message.includes('JSON')) throw parseErr;
              }
            }
          }
        }

        if (finalData && finalData.download_url) {
          progressBar.style.width = '100%';
          progressPct.textContent = '100%';
          progressPhase.textContent = 'Hoàn tất nén ZIP!';
          progressMsg.textContent = `${finalData.message || 'Đã tạo file zip thành công.'} Đang tải về máy...`;
          progressCount.textContent = '';

          // Trigger automatic browser file download
          const a = document.createElement('a');
          a.href = finalData.download_url;
          a.download = finalData.filename || 'Bao_Cao_Thuong_Nien.zip';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);

          setTimeout(() => {
            progressContainer.style.display = 'none';
          }, 3000);
        } else {
          throw new Error('Không tạo được file zip từ máy chủ.');
        }
      } catch (err) {
        progressContainer.style.display = 'none';
        alert(`Lỗi tải file zip: ${err.message}`);
      } finally {
        btnDownloadSelectedZip.disabled = selectedReports.size === 0;
        if (btnText) btnText.textContent = originalText;
      }
    });
  }

  // Clear Zenodo Cache button to free disk space
  const btnClearZenodoCache = document.getElementById('btnClearZenodoCache');
  if (btnClearZenodoCache) {
    btnClearZenodoCache.addEventListener('click', async () => {
      if (!confirm('Bạn có chắc muốn xóa toàn bộ file PDF trong bộ nhớ đệm cache để giải phóng dung lượng ổ đĩa?')) return;
      btnClearZenodoCache.disabled = true;
      btnClearZenodoCache.textContent = 'Đang dọn dẹp...';
      try {
        const res = await fetch('/api/catalog/clear-cache', { method: 'POST' });
        const data = await res.json();
        alert(`Đã dọn dẹp thành công: Đã xóa ${data.deleted_files} file PDF, giải phóng ${data.freed_mb} MB dung lượng ổ đĩa!`);
      } catch (err) {
        alert(`Lỗi dọn dẹp cache: ${err.message}`);
      } finally {
        btnClearZenodoCache.disabled = false;
        btnClearZenodoCache.textContent = 'Dọn Dẹp Cache';
      }
    });
  }

  // --------------------------------------------------------------------------
  // 3. Dictionary Studio Tab (Full CRUD)
  // --------------------------------------------------------------------------
  const dictSelectTopic = document.getElementById('dictSelectTopic');
  const dictCurrentTitle = document.getElementById('dictCurrentTitle');
  const dictCurrentSubtitle = document.getElementById('dictCurrentSubtitle');
  const dictCategoryPills = document.getElementById('dictCategoryPills');
  const dictSearchKw = document.getElementById('dictSearchKw');
  const dictTableBody = document.getElementById('dictTableBody');
  const btnAddKeyword = document.getElementById('btnAddKeyword');
  const newKwInput = document.getElementById('newKwInput');
  const newKwCategory = document.getElementById('newKwCategory');
  const newKwWeight = document.getElementById('newKwWeight');
  const btnCreateNewTopic = document.getElementById('btnCreateNewTopic');
  const uploadTopicSelect = document.getElementById('uploadTopicSelect');

  async function loadDictionariesList() {
    try {
      const res = await fetch('/api/dictionaries');
      const data = await res.json();
      const list = data.dictionaries || [];

      [dictSelectTopic, catTopicSelect, uploadTopicSelect].forEach(sel => {
        if (!sel) return;
        const currentVal = sel.value;
        sel.innerHTML = '';
        list.forEach(d => {
          const opt = document.createElement('option');
          opt.value = d.id;
          opt.textContent = `${d.name} (${d.total_keywords} từ)`;
          sel.appendChild(opt);
        });
        if (currentVal && list.some(d => d.id === currentVal)) {
          sel.value = currentVal;
        }
      });

      if (list.length > 0) {
        loadDictionaryDetail(dictSelectTopic.value || list[0].id);
      }
    } catch (err) {
      console.error('Error loading dictionaries list:', err);
    }
  }

  async function loadDictionaryDetail(topicId) {
    try {
      const res = await fetch(`/api/dictionaries/${topicId}`);
      if (!res.ok) throw new Error('Không thể tải chi tiết từ điển');
      currentDictData = await res.json();
      renderDictionaryStudio();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
    }
  }

  function renderDictionaryStudio() {
    if (!currentDictData) return;

    dictCurrentTitle.textContent = currentDictData.name;
    dictCurrentSubtitle.textContent = `Tổng cộng ${currentDictData.total_keywords} từ khóa thuộc ${currentDictData.categories.length} nhóm phân loại`;

    dictCategoryPills.innerHTML = '';
    const allPill = document.createElement('button');
    allPill.className = `pill-btn ${activeCategoryFilter === 'all' ? 'active' : ''}`;
    allPill.textContent = `Tất cả (${currentDictData.total_keywords})`;
    allPill.addEventListener('click', () => {
      activeCategoryFilter = 'all';
      renderDictionaryStudio();
    });
    dictCategoryPills.appendChild(allPill);

    currentDictData.categories.forEach(cat => {
      const count = currentDictData.keywords.filter(k => k.category === cat).length;
      const pill = document.createElement('button');
      pill.className = `pill-btn ${activeCategoryFilter === cat ? 'active' : ''}`;
      pill.textContent = `${cat} (${count})`;
      pill.addEventListener('click', () => {
        activeCategoryFilter = cat;
        renderDictionaryStudio();
      });
      dictCategoryPills.appendChild(pill);
    });

    renderKeywordsTable();
  }

  function renderKeywordsTable() {
    if (!currentDictData) return;
    const filterText = dictSearchKw.value.trim().toLowerCase();

    const filtered = currentDictData.keywords.filter(k => {
      const matchCat = activeCategoryFilter === 'all' || k.category === activeCategoryFilter;
      const matchText = !filterText || k.keyword.toLowerCase().includes(filterText);
      return matchCat && matchText;
    });

    dictTableBody.innerHTML = '';
    if (filtered.length === 0) {
      dictTableBody.innerHTML = `
        <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">
          Không có từ khóa nào khớp với bộ lọc.
        </td></tr>
      `;
      return;
    }

    filtered.forEach((k, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="tabular" style="color: var(--text-muted);">${idx + 1}</td>
        <td><strong style="color: var(--text-primary);">${escapeHtml(k.keyword)}</strong></td>
        <td><span class="badge badge-cat">${escapeHtml(k.category)}</span></td>
        <td style="text-align: right;" class="tabular">${k.weight}</td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-sm btn-edit-kw" data-kw="${escapeHtml(k.keyword)}" data-cat="${escapeHtml(k.category)}" data-w="${k.weight}">Sửa</button>
          <button class="btn btn-danger btn-sm btn-del-kw" data-kw="${escapeHtml(k.keyword)}">Xóa</button>
        </td>
      `;

      tr.querySelector('.btn-edit-kw').addEventListener('click', () => {
        handleEditKeyword(k.keyword, k.category, k.weight);
      });

      tr.querySelector('.btn-del-kw').addEventListener('click', () => {
        handleDeleteKeyword(k.keyword);
      });

      dictTableBody.appendChild(tr);
    });
  }

  async function handleAddKeyword() {
    const kw = newKwInput.value.trim();
    const cat = newKwCategory.value.trim() || 'default';
    const weight = parseFloat(newKwWeight.value) || 1.0;

    if (!kw) {
      alert('Vui lòng nhập từ khóa!');
      return;
    }

    try {
      const res = await fetch(`/api/dictionaries/${currentDictData.id}/keyword`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: kw, category: cat, weight: weight })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Không thể thêm từ khóa');
      }

      newKwInput.value = '';
      await loadDictionaryDetail(currentDictData.id);
      loadDictionariesList();
    } catch (err) {
      alert(`Lỗi thêm từ khóa: ${err.message}`);
    }
  }

  async function handleEditKeyword(oldKw, oldCat, oldWeight) {
    const newKw = prompt('Nhập từ khóa mới:', oldKw);
    if (!newKw || newKw.trim() === '') return;

    const newCat = prompt('Nhập nhóm phân loại (Category):', oldCat) || oldCat;
    const newWeightStr = prompt('Nhập trọng số (Weight):', oldWeight) || oldWeight;
    const newWeight = parseFloat(newWeightStr) || 1.0;

    try {
      const res = await fetch(`/api/dictionaries/${currentDictData.id}/keyword`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          old_keyword: oldKw,
          new_keyword: newKw.trim(),
          category: newCat.trim(),
          weight: newWeight
        })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Không thể sửa từ khóa');
      }

      await loadDictionaryDetail(currentDictData.id);
    } catch (err) {
      alert(`Lỗi sửa từ khóa: ${err.message}`);
    }
  }

  async function handleDeleteKeyword(kw) {
    if (!confirm(`Bạn có chắc muốn xóa từ khóa "${kw}" khỏi từ điển không?`)) return;

    try {
      const res = await fetch(`/api/dictionaries/${currentDictData.id}/keyword`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: kw })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Không thể xóa từ khóa');
      }

      await loadDictionaryDetail(currentDictData.id);
      loadDictionariesList();
    } catch (err) {
      alert(`Lỗi xóa từ khóa: ${err.message}`);
    }
  }

  async function handleCreateTopic() {
    const id = prompt('Nhập mã từ điển viết liền không dấu (ví dụ: ai_banking, digital_tax):');
    if (!id || id.trim() === '') return;

    const name = prompt('Nhập tên hiển thị của từ điển (ví dụ: AI & Ngân hàng số):');
    if (!name || name.trim() === '') return;

    try {
      const res = await fetch('/api/dictionaries/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: id.trim(), name: name.trim() })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Không thể tạo từ điển');
      }

      await loadDictionariesList();
      dictSelectTopic.value = id.trim().toLowerCase();
      await loadDictionaryDetail(id.trim().toLowerCase());
    } catch (err) {
      alert(`Lỗi tạo từ điển: ${err.message}`);
    }
  }

  if (dictSelectTopic) {
    dictSelectTopic.addEventListener('change', () => {
      activeCategoryFilter = 'all';
      loadDictionaryDetail(dictSelectTopic.value);
    });
  }

  if (dictSearchKw) {
    dictSearchKw.addEventListener('input', renderKeywordsTable);
  }

  if (btnAddKeyword) {
    btnAddKeyword.addEventListener('click', handleAddKeyword);
  }

  if (btnCreateNewTopic) {
    btnCreateNewTopic.addEventListener('click', handleCreateTopic);
  }

  // --------------------------------------------------------------------------
  // 4. Research Results Rendering
  // --------------------------------------------------------------------------
  const statObsCount = document.getElementById('statObsCount');
  const statHitsCount = document.getElementById('statHitsCount');
  const statMentionsCount = document.getElementById('statMentionsCount');
  const panelDataTableBody = document.getElementById('panelDataTableBody');
  const snippetsContainer = document.getElementById('snippetsContainer');
  const btnDlExcel = document.getElementById('btnDlExcel');
  const btnDlStata = document.getElementById('btnDlStata');
  const btnDlCsv = document.getElementById('btnDlCsv');

  function renderResearchResults(data) {
    statObsCount.textContent = data.total_files || 0;
    statHitsCount.textContent = data.files_with_hits || 0;
    statMentionsCount.textContent = (data.total_mentions || 0).toLocaleString();

    if (btnDlExcel) btnDlExcel.href = data.excel_download;
    if (btnDlStata) btnDlStata.href = data.stata_download;
    if (btnDlCsv) btnDlCsv.href = data.csv_download;

    panelDataTableBody.innerHTML = '';
    const rows = data.top_rows || [];
    rows.forEach(r => {
      const tr = document.createElement('tr');
      let freq = 0;
      let div = 0;
      let score = 0;

      for (const [k, v] of Object.entries(r)) {
        if (k.endsWith('_frequency')) freq = v;
        else if (k.endsWith('_diversity')) div = v;
        else if (k.endsWith('_score')) score = v;
      }

      tr.innerHTML = `
        <td><strong style="color: var(--text-primary); font-family: var(--font-mono);">${r.ticker || '—'}</strong></td>
        <td class="tabular">${r.year || '—'}</td>
        <td><span class="badge badge-cat">${escapeHtml(r.icb_level1 || '—')}</span></td>
        <td style="font-size: 12px; color: var(--text-secondary);">${escapeHtml(r.icb_level2 || '—')}</td>
        <td style="max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(r.file || '')}">
          ${escapeHtml(r.file || '')}
        </td>
        <td style="text-align: right;" class="tabular">${(r.total_words || 0).toLocaleString()}</td>
        <td style="text-align: right; font-weight: 700; color: ${freq > 0 ? 'var(--color-success)' : 'inherit'};" class="tabular">${freq}</td>
        <td style="text-align: right;" class="tabular">${div}</td>
        <td style="text-align: right;" class="tabular">${typeof score === 'number' ? score.toFixed(4) : score}</td>
      `;
      panelDataTableBody.appendChild(tr);
    });

    snippetsContainer.innerHTML = '';
    const snips = data.snippets || [];
    if (snips.length === 0) {
      snippetsContainer.innerHTML = '<p style="color: var(--text-muted); font-style: italic;">Không tìm thấy câu văn nào chứa từ khóa trong các tài liệu đã quét.</p>';
    } else {
      snips.forEach((s, idx) => {
        const item = document.createElement('div');
        item.className = 'snippet-box';
        item.innerHTML = `
          <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
            <span style="font-weight: 600; font-family: var(--font-mono);">${s.ticker || 'DN'} (${s.year || '—'})</span>
            <span class="badge badge-cat">${escapeHtml(s.category)}</span>
          </div>
          <p style="color: var(--text-secondary); line-height: 1.6;">
            "...${escapeHtml(s.context).replace(new RegExp(escapeRegExp(escapeHtml(s.keyword)), 'gi'), `<span class="snippet-kw">${escapeHtml(s.keyword)}</span>`)}..."
          </p>
        `;
        snippetsContainer.appendChild(item);
      });
    }
  }

  // --------------------------------------------------------------------------
  // 5. Personal Upload / Folder Scan
  // --------------------------------------------------------------------------
  const btnExecuteUploadScan = document.getElementById('btnExecuteUploadScan');
  const uploadFileInput = document.getElementById('uploadFileInput');
  const uploadFolderInput = document.getElementById('uploadFolderInput');

  if (btnExecuteUploadScan) {
    btnExecuteUploadScan.addEventListener('click', async () => {
      const file = uploadFileInput.files[0];
      const folder = uploadFolderInput.value.trim();
      const topic = uploadTopicSelect.value;

      if (!file && !folder) {
        alert('Vui lòng chọn 1 file báo cáo hoặc điền đường dẫn thư mục!');
        return;
      }

      btnExecuteUploadScan.disabled = true;
      btnExecuteUploadScan.textContent = 'Đang xử lý...';

      try {
        if (folder) {
          const formData = new FormData();
          formData.append('folder_path', folder);
          formData.append('topic', topic);
          const res = await fetch('/api/scan-folder', { method: 'POST', body: formData });
          if (!res.ok) throw new Error((await res.json()).detail || 'Lỗi quét thư mục');
          const data = await res.json();
          renderResearchResults(data);
        } else {
          const formData = new FormData();
          formData.append('file', file);
          formData.append('topic', topic);
          const res = await fetch('/api/scan-file', { method: 'POST', body: formData });
          if (!res.ok) throw new Error((await res.json()).detail || 'Lỗi quét file');
          const data = await res.json();
          renderResearchResults({
            total_files: 1,
            files_with_hits: Object.values(data.variables).some(v => v > 0) ? 1 : 0,
            total_mentions: data.variables[`${topic}_frequency`] || 0,
            top_rows: [{
              ticker: data.ticker,
              year: data.year,
              file: data.filename,
              total_words: data.total_words,
              ...data.variables
            }],
            snippets: data.snippets,
            excel_download: '/api/download/panel_data.xlsx',
            stata_download: '/api/download/panel_data.dta',
            csv_download: '/api/download/panel_data.csv'
          });
        }
        switchTab('tab-results');
      } catch (err) {
        alert(`Lỗi: ${err.message}`);
      } finally {
        btnExecuteUploadScan.disabled = false;
        btnExecuteUploadScan.textContent = 'Bắt Đầu Quét File';
      }
    });
  }

  // 6. Custom folder indexing into catalog
  const btnIndexCustomFolder = document.getElementById('btnIndexCustomFolder');
  const customIndexFolderInput = document.getElementById('customIndexFolderInput');
  const indexCustomResult = document.getElementById('indexCustomResult');

  if (btnIndexCustomFolder && customIndexFolderInput) {
    btnIndexCustomFolder.addEventListener('click', async () => {
      const folder = customIndexFolderInput.value.trim();
      if (!folder) {
        alert('Vui lòng nhập đường dẫn thư mục!');
        return;
      }

      btnIndexCustomFolder.disabled = true;
      btnIndexCustomFolder.textContent = 'Đang lập chỉ mục thư mục...';
      if (indexCustomResult) indexCustomResult.style.display = 'none';

      try {
        const res = await fetch('/api/catalog/add-folder', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folder_path: folder }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Không thể lập chỉ mục thư mục');
        }

        const data = await res.json();
        if (indexCustomResult) {
          indexCustomResult.textContent = `${data.message} (Tổng cộng hiện có ${data.total_local} báo cáo trên máy).`;
          indexCustomResult.style.display = 'block';
        }
        await loadSectors();
        await loadCatalog();
        alert(`${data.message}!`);
      } catch (err) {
        alert(`Lỗi: ${err.message}`);
      } finally {
        btnIndexCustomFolder.disabled = false;
        btnIndexCustomFolder.textContent = 'Lập Chỉ Mục Thư Mục Này Vào Kho';
      }
    });
  }
  // --------------------------------------------------------------------------
  // 7. Financial Data Tab (vnfinancialdata) — Full Integration
  // --------------------------------------------------------------------------
  let finSelectedItems = new Map(); // item_code -> {item_code, item_name, statement}
  let finPresetsData = [];
  let finSearchTimer = null;
  let finAllItems = []; // Full 702 items cache
  let finTabInitialized = false;

  async function loadFinancialStatus() {
    const badge = document.getElementById('finStatusBadge');
    if (!badge) return;
    try {
      const res = await fetch('/api/financial/status');
      const data = await res.json();
      if (data.available) {
        const ips = data.items_per_statement || {};
        badge.innerHTML = `<span class="badge" style="background: var(--color-success-bg); color: var(--color-success); border: 1px solid var(--color-success-border);">vnfinancialdata v${data.version} | ${data.total_items} chi tieu (BS:${ips.balance_sheet || '?'} IS:${ips.income_statement || '?'} CF:${ips.cash_flow || '?'})</span>`;

        // Show metadata panel
        const metaPanel = document.getElementById('finMetadataPanel');
        if (metaPanel) {
          metaPanel.style.display = 'block';
          document.getElementById('finMetaRevision').textContent = `Dataset: ${data.dataset_revision || '?'}`;
          document.getElementById('finMetaSchema').textContent = `Schema: ${data.schema_version || '?'}`;
          document.getElementById('finMetaExchanges').textContent = `Sàn: ${(data.supported_exchanges || []).join(', ')}`;
          const accessEl = document.getElementById('finMetaAccess');
          if (data.access) {
            accessEl.textContent = `Access: OK`;
          }
        }

        loadFinancialPresets();
        loadFinAllItems();
        loadFinancialRatios();
      } else {
        badge.innerHTML = `<span class="badge" style="background: rgba(239,68,68,0.1); color: #ef4444;">Chưa cài: ${data.install_cmd}</span>`;
      }
    } catch (e) {
      badge.innerHTML = `<span class="badge" style="background: rgba(239,68,68,0.1); color: #ef4444;">Lỗi kết nối</span>`;
    }
  }

  async function loadFinancialPresets() {
    try {
      const res = await fetch('/api/financial/presets');
      const data = await res.json();
      finPresetsData = data.presets || [];

      // Also load custom presets from localStorage
      const customPresets = JSON.parse(localStorage.getItem('arminer_custom_presets') || '[]');
      customPresets.forEach(p => { p._custom = true; finPresetsData.push(p); });

      const sel = document.getElementById('finPresetSelect');
      if (!sel) return;
      sel.innerHTML = '<option value="">-- Chọn preset --</option>';
      finPresetsData.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.name}${p._custom ? ' [Tùy chỉnh]' : ''} -- ${p.description}`;
        sel.appendChild(opt);
      });
    } catch (e) {
      console.error('Load presets error:', e);
    }
  }

  async function loadFinAllItems() {
    try {
      const res = await fetch('/api/financial/items?limit=0');
      const data = await res.json();
      finAllItems = data.items || [];
      renderFinAccordion(finAllItems);
    } catch (e) {
      console.error('Load all items error:', e);
      document.getElementById('finAccordionContainer').innerHTML = '<div style="padding: 20px; text-align: center; color: var(--color-danger);">Lỗi tải danh mục chỉ tiêu</div>';
    }
  }

  const FINANCIAL_CATEGORIES = [
    { key: 'CĐKT. TÀI SẢN NGẮN HẠN', name: 'CĐKT. TÀI SẢN NGẮN HẠN', shortLabel: 'TSNH', cls: 'bs' },
    { key: 'CĐKT. TÀI SẢN DÀI HẠN', name: 'CĐKT. TÀI SẢN DÀI HẠN', shortLabel: 'TSDH', cls: 'bs' },
    { key: 'CĐKT. NỢ PHẢI TRẢ NGẮN HẠN', name: 'CĐKT. NỢ PHẢI TRẢ NGẮN HẠN', shortLabel: 'NONH', cls: 'bs' },
    { key: 'CĐKT. NỢ PHẢI TRẢ DÀI HẠN', name: 'CĐKT. NỢ PHẢI TRẢ DÀI HẠN', shortLabel: 'NODH', cls: 'bs' },
    { key: 'CĐKT. VỐN CHỦ SỞ HỮU', name: 'CĐKT. VỐN CHỦ SỞ HỮU', shortLabel: 'VCSH', cls: 'bs' },
    { key: 'KQKD. DOANH THU, CHI PHÍ, LỢI NHUẬN', name: 'KQKD. DOANH THU, CHI PHÍ, LỢI NHUẬN', shortLabel: 'KQKD', cls: 'is' },
    { key: 'LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG KINH DOANH', name: 'LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG KINH DOANH', shortLabel: 'LCTT-KD', cls: 'cf' },
    { key: 'LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG ĐẦU TƯ', name: 'LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG ĐẦU TƯ', shortLabel: 'LCTT-ĐT', cls: 'cf' },
    { key: 'LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG TÀI CHÍNH', name: 'LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG TÀI CHÍNH', shortLabel: 'LCTT-TC', cls: 'cf' },
    { key: 'LCTT. DÒNG TIỀN THUẦN, TIỀN CUỐI KÌ', name: 'LCTT. DÒNG TIỀN THUẦN, TIỀN CUỐI KÌ', shortLabel: 'LCTT-CK', cls: 'cf' },
    { key: 'NGOẠI BẢNG. A TÀI SẢN CỦA CTCK VÀ TÀI SẢN QUẢN LÝ THEO CAM KẾT', name: 'NGOẠI BẢNG. A TÀI SẢN CỦA CTCK VÀ TÀI SẢN QUẢN LÝ THEO CAM KẾT', shortLabel: 'NB-A', cls: 'nb' },
    { key: 'NGOẠI BẢNG. B TÀI SẢN VÀ CÁC KHOẢN PHẢI TRẢ VỀ TÀI SẢN QUẢN LÝ CAM KẾT VỚI KHÁCH HÀNG', name: 'NGOẠI BẢNG. B TÀI SẢN VÀ CÁC KHOẢN PHẢI TRẢ VỀ TÀI SẢN QUẢN LÝ CAM KẾT VỚI KHÁCH HÀNG', shortLabel: 'NB-B', cls: 'nb' },
    { key: 'THUYẾT MINH. CÁC LOẠI TÀI SẢN TÀI CHÍNH', name: 'THUYẾT MINH. CÁC LOẠI TÀI SẢN TÀI CHÍNH', shortLabel: 'TM-TSTC', cls: 'tm' },
  ];

  function renderFinAccordion(items) {
    const container = document.getElementById('finAccordionContainer');
    if (!container) return;

    const catMap = new Map();
    FINANCIAL_CATEGORIES.forEach(c => {
      catMap.set(c.name, { ...c, items: [] });
    });

    items.forEach(item => {
      let cat = item.category;
      if (!cat || !catMap.has(cat)) {
        if (item.statement === 'income_statement') cat = 'KQKD. DOANH THU, CHI PHÍ, LỢI NHUẬN';
        else if (item.statement === 'cash_flow') cat = 'LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG KINH DOANH';
        else cat = 'CĐKT. TÀI SẢN NGẮN HẠN';
      }
      catMap.get(cat).items.push(item);
    });

    container.innerHTML = '';
    FINANCIAL_CATEGORIES.forEach(catDef => {
      const group = catMap.get(catDef.name);
      if (!group || group.items.length === 0) return;

      const section = document.createElement('div');
      section.className = 'fin-accordion-section';

      // Header
      const header = document.createElement('div');
      header.className = `fin-accordion-header ${group.cls}`;
      header.innerHTML = `
        <span class="fin-accordion-arrow">&#9654;</span>
        <span class="fin-stmt-badge ${group.cls}">${group.shortLabel}</span>
        <span class="fin-accordion-title" style="font-size: 12px;">${escapeHtml(group.name)}</span>
        <span class="fin-accordion-count">${group.items.length} chỉ tiêu</span>
        <button class="btn btn-secondary btn-sm fin-select-all-btn" style="margin-left: auto; font-size: 10px; padding: 2px 8px;">Chọn nhóm</button>
      `;

      // Content
      const content = document.createElement('div');
      content.className = 'fin-accordion-content';
      content.style.display = 'none';

      group.items.forEach(item => {
        const isSelected = finSelectedItems.has(item.item_code);
        const row = document.createElement('label');
        row.className = 'fin-accordion-item';
        row.dataset.itemcode = item.item_code;
        row.dataset.itemname = (item.item_name || '').toLowerCase();
        row.innerHTML = `
          <input type="checkbox" class="custom-chk" data-code="${item.item_code}" ${isSelected ? 'checked' : ''}>
          <span class="fin-item-label">${escapeHtml(item.item_name)}</span>
          <span class="fin-item-code">${item.item_code}</span>
        `;

        const chk = row.querySelector('input');
        chk.addEventListener('change', () => {
          if (chk.checked) {
            finSelectedItems.set(item.item_code, { item_code: item.item_code, item_name: item.item_name, statement: item.statement, category: item.category });
          } else {
            finSelectedItems.delete(item.item_code);
          }
          renderFinSelectedItems();
        });

        content.appendChild(row);
      });

      // Toggle accordion
      header.addEventListener('click', (e) => {
        if (e.target.classList.contains('fin-select-all-btn')) return;
        const isOpen = content.style.display !== 'none';
        content.style.display = isOpen ? 'none' : 'block';
        header.querySelector('.fin-accordion-arrow').innerHTML = isOpen ? '&#9654;' : '&#9660;';
      });

      // Select all button for this category
      header.querySelector('.fin-select-all-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        const allChecked = group.items.every(i => finSelectedItems.has(i.item_code));
        group.items.forEach(item => {
          if (allChecked) {
            finSelectedItems.delete(item.item_code);
          } else {
            finSelectedItems.set(item.item_code, { item_code: item.item_code, item_name: item.item_name, statement: item.statement, category: item.category });
          }
        });
        content.querySelectorAll('input[type="checkbox"]').forEach(chk => {
          chk.checked = !allChecked;
        });
        e.target.textContent = allChecked ? 'Chọn nhóm' : 'Bỏ chọn';
        renderFinSelectedItems();
      });

      section.appendChild(header);
      section.appendChild(content);
      container.appendChild(section);
    });
  }

  async function loadFinancialRatios() {
    const container = document.getElementById('finRatiosContainer');
    const countEl = document.getElementById('finRatiosCount');
    if (!container) return;

    try {
      const res = await fetch('/api/financial/ratios');
      const data = await res.json();
      const ratiosObj = data.ratios || {};
      const entries = Object.entries(ratiosObj);
      if (entries.length === 0) return;

      if (countEl) countEl.textContent = `(${entries.length} chỉ số)`;
      container.innerHTML = '';

      // Group by group name
      const groups = {};
      entries.forEach(([code, r]) => {
        const gName = r.group || 'Chỉ số khác';
        if (!groups[gName]) groups[gName] = [];
        groups[gName].push({ code, ...r });
      });

      const defaultChecked = new Set([
        'roa', 'roe', 'gross_margin', 'net_margin', 'ebit_margin',
        'debt_to_assets', 'debt_to_equity', 'current_ratio',
        'margin_to_equity', 'pct_margin_loans', 'pct_fvtpl',
        'rev_growth_yoy', 'eat_growth_yoy', 'assets_growth_yoy',
        'total_assets', 'equity', 'net_revenue', 'profit_after_tax',
        'operating_cash_flow', 'size_ln', 'margin_profit', 'eat_parent'
      ]);

      for (const [groupName, ratios] of Object.entries(groups)) {
        if (!ratios || ratios.length === 0) continue;

        const groupDiv = document.createElement('div');
        groupDiv.style.marginBottom = '12px';

        const titleDiv = document.createElement('div');
        titleDiv.style.fontSize = '11px';
        titleDiv.style.fontWeight = '600';
        titleDiv.style.color = 'var(--text-muted)';
        titleDiv.style.marginBottom = '6px';
        titleDiv.style.textTransform = 'uppercase';
        titleDiv.style.letterSpacing = '0.04em';
        titleDiv.textContent = `${groupName} (${ratios.length})`;
        groupDiv.appendChild(titleDiv);

        const listDiv = document.createElement('div');
        listDiv.style.display = 'flex';
        listDiv.style.flexWrap = 'wrap';
        listDiv.style.gap = '6px';

        ratios.forEach(r => {
          const isChecked = defaultChecked.has(r.code);
          const lbl = document.createElement('label');
          lbl.className = 'fin-ratio-chk';
          lbl.title = `${r.name}: ${r.formula}`;
          lbl.innerHTML = `<input type="checkbox" value="${r.code}" ${isChecked ? 'checked' : ''}> ${escapeHtml(r.name)}`;
          listDiv.appendChild(lbl);
        });

        groupDiv.appendChild(listDiv);
        container.appendChild(groupDiv);
      }
    } catch (e) {
      console.error('Load ratios error:', e);
      container.innerHTML = '<div style="color: var(--color-danger); font-size: 12px;">Lỗi tải danh mục chỉ số WiData</div>';
    }
  }

  // Client-side search filter
  const finItemSearch = document.getElementById('finItemSearch');
  if (finItemSearch) {
    finItemSearch.addEventListener('input', () => {
      clearTimeout(finSearchTimer);
      finSearchTimer = setTimeout(() => {
        const query = finItemSearch.value.trim().toLowerCase();
        const container = document.getElementById('finAccordionContainer');
        if (!container) return;

        const allItems = container.querySelectorAll('.fin-accordion-item');
        const allSections = container.querySelectorAll('.fin-accordion-section');

        if (!query) {
          // Show all
          allItems.forEach(el => el.style.display = '');
          allSections.forEach(s => {
            s.style.display = '';
            s.querySelector('.fin-accordion-content').style.display = 'none';
            s.querySelector('.fin-accordion-arrow').innerHTML = '&#9654;';
          });
          return;
        }

        allSections.forEach(section => {
          const contentEl = section.querySelector('.fin-accordion-content');
          const items = contentEl.querySelectorAll('.fin-accordion-item');
          let visibleCount = 0;

          items.forEach(el => {
            const name = el.dataset.itemname || '';
            const code = el.dataset.itemcode || '';
            const match = name.includes(query) || code.includes(query);
            el.style.display = match ? '' : 'none';
            if (match) visibleCount++;
          });

          section.style.display = visibleCount > 0 ? '' : 'none';
          if (visibleCount > 0) {
            contentEl.style.display = 'block';
            section.querySelector('.fin-accordion-arrow').innerHTML = '&#9660;';
          }
        });
      }, 250);
    });
  }

  const finPresetSelect = document.getElementById('finPresetSelect');
  if (finPresetSelect) {
    finPresetSelect.addEventListener('change', () => {
      const presetId = finPresetSelect.value;
      if (!presetId) return;
      const preset = finPresetsData.find(p => p.id === presetId);
      if (!preset) return;

      finSelectedItems.clear();
      preset.items.forEach(item => {
        finSelectedItems.set(item.code, { item_code: item.code, item_name: item.name, statement: item.statement });
      });
      renderFinSelectedItems();
      updateAccordionCheckboxes();

      // Set ratio checkboxes
      document.querySelectorAll('.fin-ratio-chk input').forEach(chk => {
        chk.checked = preset.ratios.includes(chk.value);
      });
    });
  }

  function updateAccordionCheckboxes() {
    const container = document.getElementById('finAccordionContainer');
    if (!container) return;
    container.querySelectorAll('input[type="checkbox"]').forEach(chk => {
      chk.checked = finSelectedItems.has(chk.dataset.code);
    });
  }

  function renderFinSelectedItems() {
    const container = document.getElementById('finSelectedItems');
    const countEl = document.getElementById('finSelectedCount');
    if (!container) return;

    countEl.textContent = finSelectedItems.size;

    if (finSelectedItems.size === 0) {
      container.innerHTML = '<span style="color: var(--text-muted); font-size: 12px;">Chọn chỉ tiêu từ danh mục bên trái hoặc dùng Preset</span>';
      return;
    }

    container.innerHTML = '';
    finSelectedItems.forEach((item, code) => {
      const stmtClass = code.startsWith('bs_') ? 'stmt-bs' : code.startsWith('is_') ? 'stmt-is' : 'stmt-cf';
      const chip = document.createElement('span');
      chip.className = `fin-item-chip ${stmtClass}`;
      chip.innerHTML = `${escapeHtml(item.item_name)} <span class="chip-remove" data-code="${code}">x</span>`;
      chip.querySelector('.chip-remove').addEventListener('click', () => {
        finSelectedItems.delete(code);
        renderFinSelectedItems();
        updateAccordionCheckboxes();
      });
      container.appendChild(chip);
    });
  }

  // Clear all
  const btnFinClearAll = document.getElementById('btnFinClearAll');
  if (btnFinClearAll) {
    btnFinClearAll.addEventListener('click', () => {
      finSelectedItems.clear();
      renderFinSelectedItems();
      updateAccordionCheckboxes();
    });
  }

  // Select all 702 items
  const btnFinSelectAll702 = document.getElementById('btnFinSelectAll702');
  if (btnFinSelectAll702) {
    btnFinSelectAll702.addEventListener('click', () => {
      finAllItems.forEach(item => {
        finSelectedItems.set(item.item_code, {
          item_code: item.item_code,
          item_name: item.item_name,
          statement: item.statement,
          category: item.category,
        });
      });
      renderFinSelectedItems();
      updateAccordionCheckboxes();
    });
  }

  // Expand All / Collapse All
  const btnFinExpandAll = document.getElementById('btnFinExpandAll');
  if (btnFinExpandAll) {
    btnFinExpandAll.addEventListener('click', () => {
      const container = document.getElementById('finAccordionContainer');
      if (!container) return;
      container.querySelectorAll('.fin-accordion-section').forEach(s => {
        const c = s.querySelector('.fin-accordion-content');
        if (c) c.style.display = 'block';
        const a = s.querySelector('.fin-accordion-arrow');
        if (a) a.innerHTML = '&#9660;';
      });
    });
  }

  const btnFinCollapseAll = document.getElementById('btnFinCollapseAll');
  if (btnFinCollapseAll) {
    btnFinCollapseAll.addEventListener('click', () => {
      const container = document.getElementById('finAccordionContainer');
      if (!container) return;
      container.querySelectorAll('.fin-accordion-section').forEach(s => {
        const c = s.querySelector('.fin-accordion-content');
        if (c) c.style.display = 'none';
        const a = s.querySelector('.fin-accordion-arrow');
        if (a) a.innerHTML = '&#9654;';
      });
    });
  }

  // Select all ratios / Clear ratios
  const btnFinSelectAllRatios = document.getElementById('btnFinSelectAllRatios');
  if (btnFinSelectAllRatios) {
    btnFinSelectAllRatios.addEventListener('click', () => {
      document.querySelectorAll('#finRatiosContainer input[type="checkbox"]').forEach(chk => {
        chk.checked = true;
      });
    });
  }

  const btnFinClearRatios = document.getElementById('btnFinClearRatios');
  if (btnFinClearRatios) {
    btnFinClearRatios.addEventListener('click', () => {
      document.querySelectorAll('#finRatiosContainer input[type="checkbox"]').forEach(chk => {
        chk.checked = false;
      });
    });
  }

  // Save custom preset
  const btnFinSavePreset = document.getElementById('btnFinSavePreset');
  if (btnFinSavePreset) {
    btnFinSavePreset.addEventListener('click', () => {
      if (finSelectedItems.size === 0) {
        alert('Vui lòng chọn ít nhất 1 chỉ tiêu trước khi lưu preset!');
        return;
      }
      const name = prompt('Tên preset tùy chỉnh:');
      if (!name) return;
      const id = 'custom_' + Date.now();
      const items = [];
      finSelectedItems.forEach((item, code) => {
        items.push({ code: code, name: item.item_name, statement: item.statement });
      });
      const ratios = [];
      document.querySelectorAll('.fin-ratio-chk input:checked').forEach(chk => ratios.push(chk.value));

      const preset = { id, name, description: `${items.length} chỉ tiêu`, items, ratios };

      const customPresets = JSON.parse(localStorage.getItem('arminer_custom_presets') || '[]');
      customPresets.push(preset);
      localStorage.setItem('arminer_custom_presets', JSON.stringify(customPresets));

      // Refresh presets dropdown
      loadFinancialPresets();
      alert(`Đã lưu preset "${name}" thành công!`);
    });
  }

  // Quick Preview
  const btnFinPreview = document.getElementById('btnFinPreview');
  if (btnFinPreview) {
    btnFinPreview.addEventListener('click', async () => {
      const ticker = document.getElementById('finPreviewTicker').value.trim().toUpperCase();
      if (!ticker) { alert('Vui lòng nhập mã chứng khoán!'); return; }
      const stmt = document.getElementById('finPreviewStmt').value;
      const year = parseInt(document.getElementById('finPreviewYear').value) || 2023;
      const exchange = document.getElementById('finExchangeSelect').value || 'HSX';

      btnFinPreview.disabled = true;
      btnFinPreview.textContent = 'Đang tải...';

      try {
        const res = await fetch(`/api/financial/preview?ticker=${ticker}&statement=${stmt}&exchange=${exchange}&year=${year}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        const resultEl = document.getElementById('finPreviewResult');
        resultEl.style.display = 'block';

        if (!data.items || data.items.length === 0) {
          resultEl.innerHTML = '<p style="color: var(--text-muted); padding: 10px;">Không có dữ liệu cho tiêu chí này.</p>';
          return;
        }

        const stmtShort = stmt === 'balance_sheet' ? 'BS' : stmt === 'income_statement' ? 'IS' : 'CF';
        let html = `<div style="font-size: 12px; margin-bottom: 6px; color: var(--text-muted);">${ticker} | ${stmtShort} | ${year} | ${exchange} | ${data.total} chỉ tiêu</div>`;
        html += '<table class="data-table" style="font-size: 11px;"><thead><tr><th>Chỉ tiêu</th><th>item_code</th><th style="text-align: right;">Giá trị (VNĐ)</th></tr></thead><tbody>';
        data.items.forEach(item => {
          html += `<tr>
            <td>${escapeHtml(item.item_name)}</td>
            <td style="font-size: 10px; color: var(--text-muted); font-family: var(--font-mono);">${item.item_code}</td>
            <td style="text-align: right;" class="tabular">${formatFinValue(item.value)}</td>
          </tr>`;
        });
        html += '</tbody></table>';
        resultEl.innerHTML = html;
      } catch (err) {
        document.getElementById('finPreviewResult').innerHTML = `<p style="color: var(--color-danger); padding: 10px;">Lỗi: ${err.message}</p>`;
        document.getElementById('finPreviewResult').style.display = 'block';
      } finally {
        btnFinPreview.disabled = false;
        btnFinPreview.textContent = 'Xem';
      }
    });
  }

  // Quick tag buttons for financial tickers
  document.querySelectorAll('.fin-tag-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const ticker = btn.getAttribute('data-ticker');
      const input = document.getElementById('finTickerInput');
      if (!input || !ticker) return;
      const current = input.value.trim();
      const currentTickers = current ? current.split(/[,;\s]+/).map(t => t.trim().toUpperCase()) : [];
      if (!currentTickers.includes(ticker)) {
        currentTickers.push(ticker);
        input.value = currentTickers.join(', ');
      }
      input.focus();
    });
  });

  // Query
  const btnFinQuery = document.getElementById('btnFinQuery');
  if (btnFinQuery) {
    btnFinQuery.addEventListener('click', async () => {
      const tickerStr = document.getElementById('finTickerInput').value.trim();
      if (!tickerStr) {
        alert('Vui lòng nhập ít nhất 1 mã chứng khoán!');
        return;
      }

      const tickers = tickerStr.split(/[,;\s]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
      const startYear = parseInt(document.getElementById('finYearFrom').value) || 2014;
      const endYear = parseInt(document.getElementById('finYearTo').value) || 2024;
      const itemCodes = Array.from(finSelectedItems.keys());
      const ratios = [];
      document.querySelectorAll('.fin-ratio-chk input:checked').forEach(chk => ratios.push(chk.value));
      const exchange = document.getElementById('finExchangeSelect').value || null;

      if (itemCodes.length === 0) {
        alert('Vui lòng chọn ít nhất 1 chỉ tiêu tài chính hoặc dùng Preset!');
        return;
      }

      btnFinQuery.disabled = true;
      btnFinQuery.textContent = 'Đang tải...';

      const pc = document.getElementById('finProgressContainer');
      const pb = document.getElementById('finProgressBar');
      const pp = document.getElementById('finProgressPct');
      const pphs = document.getElementById('finProgressPhase');
      const pmsg = document.getElementById('finProgressMsg');
      pc.style.display = 'block';
      pb.style.width = '10%';
      pp.textContent = '';
      pphs.textContent = 'Đang tải dữ liệu từ HuggingFace...';
      pmsg.textContent = `${tickers.length} mã x ${endYear - startYear + 1} năm x ${itemCodes.length} chỉ tiêu`;

      try {
        const body = { tickers, start_year: startYear, end_year: endYear, item_codes: itemCodes, ratios };
        if (exchange) body.exchange = exchange;

        const response = await fetch('/api/financial/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalData = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data:')) {
              const jsonStr = line.slice(5).trim();
              if (!jsonStr) continue;
              try {
                const ev = JSON.parse(jsonStr);
                if (ev.total_rows !== undefined) {
                  finalData = ev;
                } else if (ev.detail) {
                  throw new Error(ev.detail);
                } else if (ev.phase) {
                  const labels = { loading: 'Tải dữ liệu', processing: 'Xử lý định dạng Panel (Pivot)' };
                  pphs.textContent = labels[ev.phase] || ev.phase;
                  pmsg.textContent = ev.message || '';
                  pb.style.width = ev.phase === 'processing' ? '60%' : '30%';
                }
              } catch (pe) {
                if (pe.message && !pe.message.includes('JSON')) throw pe;
              }
            }
          }
        }

        if (finalData) {
          pb.style.width = '100%';
          pp.textContent = '100%';
          pphs.textContent = 'Hoàn tất!';
          pmsg.textContent = `${finalData.total_rows} dòng, ${finalData.total_tickers} mã, ${finalData.year_range[0]}-${finalData.year_range[1]}`;

          setTimeout(() => { pc.style.display = 'none'; }, 1500);
          renderFinResults(finalData);
        } else {
          throw new Error('Không nhận được kết quả.');
        }
      } catch (err) {
        pc.style.display = 'none';
        alert(`Lỗi: ${err.message}`);
      } finally {
        btnFinQuery.disabled = false;
        btnFinQuery.textContent = 'Tải Dữ Liệu';
      }
    });
  }

  function formatFinValue(val) {
    if (val === null || val === undefined) return '--';
    const num = parseFloat(val);
    if (isNaN(num)) return String(val);
    if (Math.abs(num) >= 1e12) return (num / 1e12).toFixed(2) + ' nghìn tỷ';
    if (Math.abs(num) >= 1e9) return (num / 1e9).toFixed(2) + ' tỷ';
    if (Math.abs(num) >= 1e6) return (num / 1e6).toFixed(1) + ' triệu';
    if (Math.abs(num) < 100) return num.toFixed(4);
    return num.toLocaleString('vi-VN');
  }

  function renderFinResults(data) {
    const card = document.getElementById('finResultsCard');
    const thead = document.getElementById('finResultsHead');
    const tbody = document.getElementById('finResultsBody');
    const summary = document.getElementById('finResultsSummary');
    card.style.display = 'block';

    summary.textContent = `${data.total_rows} quan sát (${data.total_tickers} mã x ${data.year_range[0]}-${data.year_range[1]}) | ${data.columns.length} biến`;

    document.getElementById('finDlCsv').href = data.csv_download;
    document.getElementById('finDlXlsx').href = data.xlsx_download;
    const finXlsmEl = document.getElementById('finDlXlsm');
    if (finXlsmEl) {
      if (data.xlsm_download) {
        finXlsmEl.href = data.xlsm_download;
        finXlsmEl.style.display = 'inline-flex';
      } else {
        finXlsmEl.style.display = 'none';
      }
    }
    const finDtaEl = document.getElementById('finDlDta');
    if (finDtaEl) finDtaEl.href = data.dta_download || '#';

    // Header
    let headerHtml = '<tr><th>Mã CK</th><th>Năm</th>';
    data.columns.forEach(col => {
      const label = col.is_ratio ? `<strong>${col.name}</strong>` : col.name;
      headerHtml += `<th style="text-align: right; max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(col.code)}">${label}</th>`;
    });
    headerHtml += '</tr>';
    thead.innerHTML = headerHtml;

    // Body
    tbody.innerHTML = '';
    (data.preview || []).forEach(row => {
      const tr = document.createElement('tr');
      let html = `<td><strong style="font-family: var(--font-mono);">${row.ticker || '--'}</strong></td>`;
      html += `<td class="tabular">${row.year || '--'}</td>`;
      data.columns.forEach(col => {
        const val = row[col.code];
        const fmt = formatFinValue(val);
        const style = col.is_ratio ? 'font-weight: 600; color: var(--brand-primary);' : '';
        html += `<td style="text-align: right; ${style}" class="tabular" title="${val !== null ? val : ''}">${fmt}</td>`;
      });
      tr.innerHTML = html;
      tbody.appendChild(tr);
    });
  }

  // Merge
  const btnFinMerge = document.getElementById('btnFinMerge');
  if (btnFinMerge) {
    btnFinMerge.addEventListener('click', async () => {
      btnFinMerge.disabled = true;
      btnFinMerge.textContent = 'Đang kết hợp dữ liệu...';
      try {
        const res = await fetch('/api/financial/merge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mining_source: 'latest' }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Lỗi kết hợp dữ liệu');
        }
        const data = await res.json();

        const mergeCard = document.getElementById('finMergeCard');
        mergeCard.style.display = 'block';
        document.getElementById('finMergeSummary').textContent =
          `${data.total_rows} dòng (Mining: ${data.mining_rows} x Tài chính: ${data.financial_rows}). ` +
          `Tải file đã kết hợp bên dưới.`;
        document.getElementById('mergeDlCsv').href = data.csv_download;
        document.getElementById('mergeDlXlsx').href = data.xlsx_download;
        const mergeDtaEl = document.getElementById('mergeDlDta');
        if (mergeDtaEl) mergeDtaEl.href = data.dta_download || '#';

        alert(`Kết hợp thành công! ${data.total_rows} dòng dữ liệu bảng (panel data) hoàn chỉnh.`);
      } catch (err) {
        alert(`Lỗi: ${err.message}`);
      } finally {
        btnFinMerge.disabled = false;
        btnFinMerge.textContent = 'Kết Hợp Với Mining';
      }
    });
  }

  // Helper utils

  function escapeHtml(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // Initial Boot
  loadSectors();
  loadCatalog();
  loadDictionariesList();
  loadFinancialStatus();
});
