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
            const catalogResults = document.getElementById('catalogResultsCard');
            if (catalogResults) {
              catalogResults.style.display = 'block';
              catalogResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
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
  const newKwVariants = document.getElementById('newKwVariants');
  const newKwCategory = document.getElementById('newKwCategory');
  const btnCreateNewTopic = document.getElementById('btnCreateNewTopic');
  const btnDeleteTopic = document.getElementById('btnDeleteTopic');
  const uploadTopicSelect = document.getElementById('uploadTopicSelect');

  async function loadDictionariesList() {
    try {
      const res = await fetch('/api/dictionaries');
      const data = await res.json();
      const list = data.dictionaries || [];

      const newsTopicSelect = document.getElementById('newsTopicSelect');
      const pasteTopicSelect = document.getElementById('pasteTopicSelect');

      [dictSelectTopic, catTopicSelect, uploadTopicSelect, newsTopicSelect, pasteTopicSelect].forEach(sel => {
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
      let varHtml = '<span style="color: var(--text-muted); font-style: italic; font-size: 11px;">—</span>';
      if (k.variants && k.variants.trim()) {
        const parts = k.variants.split('|').map(v => v.trim()).filter(Boolean);
        if (parts.length > 0) {
          varHtml = parts.map(p => `<span class="var-chip">${escapeHtml(p)}</span>`).join('');
        }
      }
      tr.innerHTML = `
        <td class="tabular" style="color: var(--text-muted);">${idx + 1}</td>
        <td><strong style="color: var(--text-primary);">${escapeHtml(k.keyword)}</strong></td>
        <td>${varHtml}</td>
        <td><span class="badge badge-cat">${escapeHtml(k.category)}</span></td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-sm btn-edit-kw" data-kw="${escapeHtml(k.keyword)}" data-cat="${escapeHtml(k.category)}" data-var="${escapeHtml(k.variants || '')}">Sửa</button>
          <button class="btn btn-danger btn-sm btn-del-kw" data-kw="${escapeHtml(k.keyword)}">Xóa</button>
        </td>
      `;

      tr.querySelector('.btn-edit-kw').addEventListener('click', () => {
        handleEditKeyword(k.keyword, k.category, k.variants || '');
      });

      tr.querySelector('.btn-del-kw').addEventListener('click', () => {
        handleDeleteKeyword(k.keyword);
      });

      dictTableBody.appendChild(tr);
    });
  }

  async function handleAddKeyword() {
    const kw = newKwInput.value.trim();
    const variants = newKwVariants ? newKwVariants.value.trim() : '';
    const cat = newKwCategory.value.trim() || 'default';

    if (!kw) {
      alert('Vui lòng nhập từ khóa!');
      return;
    }

    try {
      const res = await fetch(`/api/dictionaries/${currentDictData.id}/keyword`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: kw, category: cat, weight: 1.0, variants: variants })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Không thể thêm từ khóa');
      }

      newKwInput.value = '';
      if (newKwVariants) newKwVariants.value = '';
      await loadDictionaryDetail(currentDictData.id);
      loadDictionariesList();
    } catch (err) {
      alert(`Lỗi thêm từ khóa: ${err.message}`);
    }
  }

  async function handleEditKeyword(oldKw, oldCat, oldVariants = '') {
    const newKw = prompt('Nhập từ khóa mới:', oldKw);
    if (!newKw || newKw.trim() === '') return;

    const newVariants = prompt('Nhập biến thể (variants, cách nhau dấu |):', oldVariants);
    if (newVariants === null) return;

    const newCat = prompt('Nhập nhóm phân loại (Category):', oldCat) || oldCat;

    try {
      const res = await fetch(`/api/dictionaries/${currentDictData.id}/keyword`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          old_keyword: oldKw,
          new_keyword: newKw.trim(),
          category: newCat.trim(),
          weight: 1.0,
          variants: newVariants.trim()
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

  async function handleDeleteTopic() {
    if (!currentDictData || !currentDictData.id) {
      alert('Chưa chọn bộ từ điển nào để xóa.');
      return;
    }

    const topicId = currentDictData.id;
    const topicName = currentDictData.name || topicId;

    if (!confirm(`Bạn có chắc chắn muốn XÓA HOÀN TOÀN bộ từ điển "${topicName}" (${topicId}) không?\nThao tác này sẽ xóa vĩnh viễn tệp từ điển này khỏi hệ thống!`)) {
      return;
    }

    try {
      const res = await fetch(`/api/dictionaries/${topicId}`, {
        method: 'DELETE',
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Không thể xóa bộ từ điển');
      }

      alert(`Đã xóa thành công bộ từ điển "${topicName}"!`);
      await loadDictionariesList();
    } catch (err) {
      alert(`Lỗi khi xóa bộ từ điển: ${err.message}`);
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

  if (btnDeleteTopic) {
    btnDeleteTopic.addEventListener('click', handleDeleteTopic);
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
    const catalogResults = document.getElementById('catalogResultsCard');
    if (catalogResults) catalogResults.style.display = 'block';

    statObsCount.textContent = data.total_files || 0;
    statHitsCount.textContent = data.files_with_hits || 0;
    statMentionsCount.textContent = (data.total_mentions || 0).toLocaleString();

    const resultsTabBadge = document.getElementById('resultsTabBadge');
    if (resultsTabBadge) {
      const n = data.total_files || (data.top_rows ? data.top_rows.length : 0);
      resultsTabBadge.textContent = n;
      resultsTabBadge.style.display = n > 0 ? 'inline-flex' : 'none';
    }

    if (btnDlExcel) btnDlExcel.href = data.excel_download;
    if (btnDlStata) btnDlStata.href = data.stata_download;
    if (btnDlCsv) btnDlCsv.href = data.csv_download;

    panelDataTableBody.innerHTML = '';
    const rows = data.top_rows || [];
    rows.forEach(r => {
      const tr = document.createElement('tr');
      let freq = 0;
      let logFreq = 0;
      let mention = 0;
      let density = 0;
      let wordCount = r.Word_Count ?? r.total_words ?? 0;

      for (const [k, v] of Object.entries(r)) {
        const kLower = k.toLowerCase();
        if (kLower.endsWith('_frequency') && !kLower.endsWith('_log_frequency')) freq = v;
        else if (kLower.endsWith('_log_frequency')) logFreq = v;
        else if (kLower.endsWith('_mention')) mention = v;
        else if (kLower.endsWith('_density')) density = v;
      }

      tr.innerHTML = `
        <td><strong style="color: var(--text-primary); font-family: var(--font-mono);">${r.ticker || '—'}</strong></td>
        <td class="tabular">${r.year || '—'}</td>
        <td><span class="badge badge-cat">${escapeHtml(r.icb_level1 || '—')}</span></td>
        <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(r.file || '')}">
          ${escapeHtml(r.file || '')}
        </td>
        <td style="text-align: right;" class="tabular">${(wordCount || 0).toLocaleString()}</td>
        <td style="text-align: right; font-weight: 700; color: ${freq > 0 ? 'var(--color-success)' : 'inherit'};" class="tabular">${freq}</td>
        <td style="text-align: right; font-weight: 700; color: #3b82f6;" class="tabular">${typeof logFreq === 'number' ? logFreq.toFixed(4) : logFreq}</td>
        <td style="text-align: center;">${mention > 0 ? '<span style="color: var(--color-success); font-weight: 700;">1</span>' : '<span style="color: var(--text-muted);">0</span>'}</td>
        <td style="text-align: right;" class="tabular">${typeof density === 'number' ? density.toFixed(4) : density}%</td>
      `;
      panelDataTableBody.appendChild(tr);
    });

    snippetsContainer.innerHTML = '';
    const snips = data.snippets || [];
    if (snips.length === 0) {
      snippetsContainer.innerHTML = '<p style="color: var(--text-muted); font-style: italic; padding: 12px 0;">Không tìm thấy câu văn nào chứa từ khóa trong các tài liệu đã quét.</p>';
    } else {
      snips.forEach((s, idx) => {
        const item = document.createElement('div');
        item.className = 'snippet-box';
        item.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-weight: 600; font-family: var(--font-mono); color: var(--text-primary);">${s.ticker || 'DN'} (${s.year || '—'})</span>
              <span class="badge badge-cat">${escapeHtml(s.category)}</span>
            </div>
            <button class="btn btn-secondary btn-sm btn-copy-snippet" title="Sao chép đoạn trích dẫn này">Sao chép</button>
          </div>
          <p style="color: var(--text-secondary); line-height: 1.6;">
            "...${escapeHtml(s.context).replace(new RegExp(escapeRegExp(escapeHtml(s.keyword)), 'gi'), `<span class="snippet-kw">${escapeHtml(s.keyword)}</span>`)}..."
          </p>
        `;
        const copyBtn = item.querySelector('.btn-copy-snippet');
        if (copyBtn) {
          copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(s.context).then(() => {
              copyBtn.textContent = 'Đã chép!';
              setTimeout(() => { copyBtn.textContent = 'Sao chép'; }, 1500);
            }).catch(() => {
              copyBtn.textContent = 'Lỗi copy';
            });
          });
        }
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
        const catalogResults = document.getElementById('catalogResultsCard');
        if (catalogResults) {
          catalogResults.style.display = 'block';
          switchTab('tab-catalog');
          catalogResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
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
  let finSectorTree = []; // ICB L1->L2->tickers
  let finSelectedTickers = new Set(); // Set of ticker strings
  let finSmartFilterActive = false;
  let finAvailableItemCodes = null; // Set<string> or null

  async function loadFinancialStatus() {
    const badge = document.getElementById('finStatusBadge');
    if (!badge) return;
    try {
      const res = await fetch('/api/financial/status');
      const data = await res.json();
      if (data.available) {
        badge.innerHTML = `<span class="badge" style="background: var(--color-success-bg); color: var(--color-success); border: 1px solid var(--color-success-border);">vnfinancialdata v${data.version}</span>`;

        loadFinancialPresets();
        loadFinAllItems();
        loadFinancialRatios();
        loadFinSectors();
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
        'roa', 'roe', 'gross_margin', 'net_margin',
        'debt_to_assets', 'debt_to_equity', 'current_ratio', 'size_ln'
      ]);

      for (const [groupName, ratios] of Object.entries(groups)) {
        if (!ratios || ratios.length === 0) continue;

        const groupDiv = document.createElement('div');
        groupDiv.className = 'fin-ratio-group';
        groupDiv.style.marginBottom = '12px';

        const titleDiv = document.createElement('div');
        titleDiv.className = 'fin-ratio-group-title';
        titleDiv.dataset.groupName = groupName;
        titleDiv.dataset.total = ratios.length;
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
          lbl.dataset.code = r.code;
          lbl.title = `${r.name}: ${r.formula}`;
          lbl.innerHTML = `<input type="checkbox" value="${r.code}" ${isChecked ? 'checked' : ''}> ${escapeHtml(r.name)}`;
          listDiv.appendChild(lbl);
        });

        groupDiv.appendChild(listDiv);
        container.appendChild(groupDiv);
      }
    } catch (e) {
      console.error('Load ratios error:', e);
      container.innerHTML = '<div style="color: var(--color-danger); font-size: 12px;">Lỗi tải danh mục chỉ số tài chính</div>';
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

  // Select all items (respecting smart filter if active)
  const btnFinSelectAll702 = document.getElementById('btnFinSelectAll702');
  if (btnFinSelectAll702) {
    btnFinSelectAll702.addEventListener('click', () => {
      const itemsToSelect = (finSmartFilterActive && finAvailableItemCodes)
        ? finAllItems.filter(item => finAvailableItemCodes.has(item.item_code))
        : finAllItems;

      itemsToSelect.forEach(item => {
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

  // Select core ratios / Select all ratios / Clear ratios
  const CORE_RATIOS_SET = new Set([
    'roa', 'roe', 'gross_margin', 'net_margin',
    'debt_to_assets', 'debt_to_equity', 'current_ratio', 'size_ln'
  ]);

  const btnFinSelectCoreRatios = document.getElementById('btnFinSelectCoreRatios');
  if (btnFinSelectCoreRatios) {
    btnFinSelectCoreRatios.addEventListener('click', () => {
      document.querySelectorAll('#finRatiosContainer .fin-ratio-chk').forEach(lbl => {
        const chk = lbl.querySelector('input[type="checkbox"]');
        if (chk) {
          chk.checked = CORE_RATIOS_SET.has(chk.value);
        }
      });
    });
  }

  const btnFinSelectAllRatios = document.getElementById('btnFinSelectAllRatios');
  if (btnFinSelectAllRatios) {
    btnFinSelectAllRatios.addEventListener('click', () => {
      document.querySelectorAll('#finRatiosContainer .fin-ratio-chk').forEach(lbl => {
        if (lbl.style.display !== 'none') {
          const chk = lbl.querySelector('input[type="checkbox"]');
          if (chk) chk.checked = true;
        }
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

  // ─── Sector Loading & Cascade for BCTC Tab ───
  window.vnfSupportedTickers = new Set();
  window.vnfNotableMissing = {};

  async function loadFinSectors() {
    try {
      // Load both sector taxonomy and full supported tickers set
      const [secRes, suppRes] = await Promise.all([
        fetch('/api/financial/tickers-by-sector'),
        fetch('/api/financial/supported-tickers').catch(() => null)
      ]);
      const data = await secRes.json();
      finSectorTree = data.sectors || [];

      if (suppRes && suppRes.ok) {
        const suppData = await suppRes.json();
        window.vnfSupportedTickers = new Set(suppData.supported_tickers || []);
        window.vnfNotableMissing = suppData.notable_missing || {};
      }

      const l1Sel = document.getElementById('finSectorL1');
      if (!l1Sel) return;
      l1Sel.innerHTML = '<option value="">Tất cả ngành</option>';
      finSectorTree.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.name;
        opt.textContent = `${s.name} (${s.total_tickers} mã)`;
        l1Sel.appendChild(opt);
      });
    } catch (e) {
      console.error('Load fin sectors error:', e);
    }
  }

  // L1 → L2 cascade
  const finSectorL1 = document.getElementById('finSectorL1');
  if (finSectorL1) {
    finSectorL1.addEventListener('change', () => {
      const l2Sel = document.getElementById('finSectorL2');
      l2Sel.innerHTML = '<option value="">Tất cả phân ngành</option>';
      const selectedL1 = finSectorL1.value;
      if (!selectedL1) return;
      const found = finSectorTree.find(s => s.name === selectedL1);
      if (found && found.subsectors) {
        found.subsectors.forEach(sub => {
          const opt = document.createElement('option');
          opt.value = sub.name;
          opt.textContent = `${sub.name} (${sub.ticker_count} mã)`;
          l2Sel.appendChild(opt);
        });
      }
    });
  }

  // "Thêm ngành" button
  const btnFinAddSector = document.getElementById('btnFinAddSector');
  if (btnFinAddSector) {
    btnFinAddSector.addEventListener('click', () => {
      const l1 = document.getElementById('finSectorL1').value;
      const l2 = document.getElementById('finSectorL2').value;
      if (!l1) { alert('Vui lòng chọn ngành ICB L1 trước!'); return; }
      const found = finSectorTree.find(s => s.name === l1);
      if (!found) return;
      let tickersToAdd = [];
      if (l2) {
        const sub = found.subsectors.find(s => s.name === l2);
        if (sub) tickersToAdd = sub.tickers || [];
      } else {
        found.subsectors.forEach(sub => {
          tickersToAdd.push(...(sub.tickers || []));
        });
      }
      tickersToAdd.forEach(t => finSelectedTickers.add(t.toUpperCase()));
      renderFinTickerPills();
    });
  }

  // "+ Tất cả mã" button — Select all tickers from all sectors
  const btnFinAddAllTickers = document.getElementById('btnFinAddAllTickers');
  if (btnFinAddAllTickers) {
    btnFinAddAllTickers.addEventListener('click', () => {
      finSectorTree.forEach(s => {
        (s.subsectors || []).forEach(sub => {
          (sub.tickers || []).forEach(t => {
            finSelectedTickers.add(t.toUpperCase());
          });
        });
      });
      renderFinTickerPills();
    });
  }

  // Ticker input — Enter to add
  const finTickerInputEl = document.getElementById('finTickerInput');
  if (finTickerInputEl) {
    finTickerInputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const val = finTickerInputEl.value.trim();
        if (!val) return;
        const tickers = val.split(/[,;\s]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
        tickers.forEach(t => finSelectedTickers.add(t));
        finTickerInputEl.value = '';
        renderFinTickerPills();
      }
    });
  }

  // Clear all tickers
  const btnFinClearTickers = document.getElementById('btnFinClearTickers');
  if (btnFinClearTickers) {
    btnFinClearTickers.addEventListener('click', () => {
      finSelectedTickers.clear();
      renderFinTickerPills();
    });
  }

  // Button: Remove all missing tickers with 1-click
  const btnRemoveMissingTickers = document.getElementById('btnRemoveMissingTickers');
  if (btnRemoveMissingTickers) {
    btnRemoveMissingTickers.addEventListener('click', () => {
      if (window.vnfSupportedTickers && window.vnfSupportedTickers.size > 0) {
        const toDelete = [];
        finSelectedTickers.forEach(t => {
          if (!window.vnfSupportedTickers.has(t)) toDelete.push(t);
        });
        toDelete.forEach(t => finSelectedTickers.delete(t));
        renderFinTickerPills();
      }
    });
  }

  let finPillsExpanded = false;
  function renderFinTickerPills() {
    const container = document.getElementById('finTickerPills');
    if (!container) return;
    container.innerHTML = '';

    const alertBox = document.getElementById('finMissingTickersAlert');

    if (finSelectedTickers.size === 0) {
      container.innerHTML = '<span class="fin-pills-placeholder">Chọn ngành hoặc nhập mã CK ở trên để thêm doanh nghiệp</span>';
      if (alertBox) alertBox.style.display = 'none';
      updateFinQuerySummary();
      return;
    }

    const tickerArray = Array.from(finSelectedTickers);
    const maxVisible = finPillsExpanded ? tickerArray.length : 30;
    const visibleTickers = tickerArray.slice(0, maxVisible);

    // Detect missing tickers against supported set
    const missingTickers = [];
    if (window.vnfSupportedTickers && window.vnfSupportedTickers.size > 0) {
      tickerArray.forEach(t => {
        if (!window.vnfSupportedTickers.has(t)) {
          missingTickers.push(t);
        }
      });
    }

    // Toggle missing alert box
    if (alertBox) {
      if (missingTickers.length > 0) {
        alertBox.style.display = 'block';
        const cntEl = document.getElementById('finMissingCount');
        if (cntEl) cntEl.textContent = missingTickers.length;
        const listEl = document.getElementById('finMissingList');
        if (listEl) listEl.textContent = missingTickers.join(', ');
      } else {
        alertBox.style.display = 'none';
      }
    }

    // Summary badge
    const countBadge = document.createElement('span');
    countBadge.style.cssText = 'font-size: 11px; font-weight: 700; color: var(--brand-primary); background: rgba(99,102,241,0.12); padding: 2px 8px; border-radius: 12px; margin-right: 4px;';
    countBadge.textContent = `${tickerArray.length} mã${missingTickers.length > 0 ? ` (${missingTickers.length} mã khuyết)` : ''}`;
    container.appendChild(countBadge);

    visibleTickers.forEach(ticker => {
      const isMissing = window.vnfSupportedTickers && window.vnfSupportedTickers.size > 0 && !window.vnfSupportedTickers.has(ticker);
      const pill = document.createElement('span');
      pill.className = 'fin-ticker-pill';

      if (isMissing) {
        pill.style.cssText = 'background: rgba(239, 68, 68, 0.1); color: #DC2626; border: 1px solid rgba(239, 68, 68, 0.35); font-weight: 600;';
        pill.title = 'Mã này không có trong vnfinancialdata (sẽ không có số liệu BCTC)';
        pill.innerHTML = `⚠️ ${escapeHtml(ticker)} <span class="pill-remove" data-ticker="${ticker}" style="color: #DC2626;">×</span>`;
      } else {
        pill.innerHTML = `${escapeHtml(ticker)} <span class="pill-remove" data-ticker="${ticker}">×</span>`;
      }

      pill.querySelector('.pill-remove').addEventListener('click', () => {
        finSelectedTickers.delete(ticker);
        renderFinTickerPills();
      });
      container.appendChild(pill);
    });

    if (tickerArray.length > 30) {
      const toggleBtn = document.createElement('button');
      toggleBtn.className = 'btn btn-secondary btn-sm';
      toggleBtn.style.cssText = 'font-size: 11px; padding: 2px 8px; border-radius: 12px; margin-left: 4px;';
      toggleBtn.textContent = finPillsExpanded ? 'Thu gọn' : `Xem thêm ${tickerArray.length - 30} mã...`;
      toggleBtn.addEventListener('click', () => {
        finPillsExpanded = !finPillsExpanded;
        renderFinTickerPills();
      });
      container.appendChild(toggleBtn);
    }

    updateFinQuerySummary();
  }

  function updateFinQuerySummary() {
    const el = document.getElementById('finQuerySummary');
    if (!el) return;
    const nTickers = finSelectedTickers.size;
    const nItems = finSelectedItems.size;
    const y1 = document.getElementById('finYearFrom')?.value || '2014';
    const y2 = document.getElementById('finYearTo')?.value || '2024';
    if (nTickers === 0) {
      el.textContent = '';
    } else {
      el.textContent = `${nTickers} mã × ${nItems || '?'} chỉ tiêu × (${y1}–${y2})`;
    }
  }

  // ─── Smart Filter: Only show items that actually exist for the selected tickers ───
  const btnFinSmartFilter = document.getElementById('btnFinSmartFilter');
  const btnFinShowAll702 = document.getElementById('btnFinShowAll702');
  const finSmartFilterBadge = document.getElementById('finSmartFilterBadge');

  if (btnFinSmartFilter) {
    btnFinSmartFilter.addEventListener('click', async () => {
      if (finSelectedTickers.size === 0) {
        alert('Vui lòng chọn ít nhất 1 mã CK trước!');
        return;
      }
      // Probe up to 10 selected tickers for comprehensive discovery
      const probeTickers = Array.from(finSelectedTickers).slice(0, 10).join(',');
      const exchange = document.getElementById('finExchangeSelect').value || '';
      btnFinSmartFilter.disabled = true;
      btnFinSmartFilter.textContent = 'Đang dò...';

      try {
        const res = await fetch(`/api/financial/available-items?ticker=${encodeURIComponent(probeTickers)}&exchange=${exchange}`);
        const data = await res.json();
        finAvailableItemCodes = new Set(data.item_codes || []);

        // Apply filter to accordion
        const container = document.getElementById('finAccordionContainer');
        container.classList.add('fin-smart-filter-active');
        let visibleCount = 0;

        container.querySelectorAll('.fin-accordion-section').forEach(section => {
          const content = section.querySelector('.fin-accordion-content');
          let sectionVisible = 0;
          content.querySelectorAll('.fin-accordion-item').forEach(item => {
            const code = item.dataset.itemcode;
            if (finAvailableItemCodes.has(code)) {
              item.classList.remove('fin-item-hidden');
              sectionVisible++;
              visibleCount++;
            } else {
              item.classList.add('fin-item-hidden');
            }
          });
          if (sectionVisible === 0) {
            section.classList.add('fin-section-empty');
          } else {
            section.classList.remove('fin-section-empty');
            const countEl = section.querySelector('.fin-accordion-count');
            if (countEl) countEl.textContent = `${sectionVisible} chỉ tiêu`;
          }
        });

        finSmartFilterActive = true;
        if (btnFinShowAll702) btnFinShowAll702.style.display = 'inline-flex';
        if (finSmartFilterBadge) {
          finSmartFilterBadge.style.display = 'inline';
          const tickerDisplay = probeTickers.length > 20 ? probeTickers.slice(0, 20) + '...' : probeTickers;
          finSmartFilterBadge.textContent = `Đã lọc: ${visibleCount}/${finAllItems.length} chỉ tiêu có số liệu (${tickerDisplay})`;
        }
        if (btnFinSelectAll702) {
          btnFinSelectAll702.textContent = `Chọn tất cả (${visibleCount})`;
        }

        // Apply filter to financial ratios based on calculable prerequisites
        if (data.available_ratios) {
          const availRatiosSet = new Set(data.available_ratios);
          const ratioContainer = document.getElementById('finRatiosContainer');
          if (ratioContainer) {
            ratioContainer.querySelectorAll('.fin-ratio-group').forEach(group => {
              let groupVisible = 0;
              group.querySelectorAll('.fin-ratio-chk').forEach(lbl => {
                const code = lbl.dataset.code;
                if (availRatiosSet.has(code)) {
                  lbl.style.display = 'inline-flex';
                  groupVisible++;
                } else {
                  lbl.style.display = 'none';
                  const chk = lbl.querySelector('input[type="checkbox"]');
                  if (chk) chk.checked = false;
                }
              });
              const titleEl = group.querySelector('.fin-ratio-group-title');
              if (groupVisible === 0) {
                group.style.display = 'none';
              } else {
                group.style.display = 'block';
                if (titleEl) {
                  titleEl.textContent = `${titleEl.dataset.groupName} (${groupVisible}/${titleEl.dataset.total})`;
                }
              }
            });
            const finRatiosCount = document.getElementById('finRatiosCount');
            if (finRatiosCount) {
              const totalRatios = Object.keys(finAvailableRatios || {}).length || 116;
              finRatiosCount.textContent = `(${data.total_ratios || data.available_ratios.length}/${totalRatios} khả dụng)`;
            }
          }
        }
      } catch (err) {
        alert(`Lỗi: ${err.message}`);
      } finally {
        btnFinSmartFilter.disabled = false;
        btnFinSmartFilter.textContent = 'Lọc theo DN';
      }
    });
  }

  if (btnFinShowAll702) {
    btnFinShowAll702.addEventListener('click', () => {
      const container = document.getElementById('finAccordionContainer');
      container.classList.remove('fin-smart-filter-active');
      container.querySelectorAll('.fin-item-hidden').forEach(el => el.classList.remove('fin-item-hidden'));
      container.querySelectorAll('.fin-section-empty').forEach(el => el.classList.remove('fin-section-empty'));
      renderFinAccordion(finAllItems);
      finSmartFilterActive = false;
      finAvailableItemCodes = null;
      btnFinShowAll702.style.display = 'none';
      if (finSmartFilterBadge) finSmartFilterBadge.style.display = 'none';
      if (btnFinSelectAll702) btnFinSelectAll702.textContent = 'Chọn tất cả';

      // Reset financial ratios container
      const ratioContainer = document.getElementById('finRatiosContainer');
      if (ratioContainer) {
        ratioContainer.querySelectorAll('.fin-ratio-group').forEach(group => {
          group.style.display = 'block';
          group.querySelectorAll('.fin-ratio-chk').forEach(lbl => {
            lbl.style.display = 'inline-flex';
          });
          const titleEl = group.querySelector('.fin-ratio-group-title');
          if (titleEl) {
            titleEl.textContent = `${titleEl.dataset.groupName} (${titleEl.dataset.total})`;
          }
        });
        const finRatiosCount = document.getElementById('finRatiosCount');
        if (finRatiosCount) {
          const totalRatios = Object.keys(finAvailableRatios || {}).length || 116;
          finRatiosCount.textContent = `(${totalRatios} chỉ số)`;
        }
      }
    });
  }

  // Query
  const btnFinQuery = document.getElementById('btnFinQuery');
  if (btnFinQuery) {
    btnFinQuery.addEventListener('click', async () => {
      const leftover = document.getElementById('finTickerInput').value.trim();
      if (leftover) {
        leftover.split(/[,;\s]+/).map(t => t.trim().toUpperCase()).filter(Boolean).forEach(t => finSelectedTickers.add(t));
        document.getElementById('finTickerInput').value = '';
        renderFinTickerPills();
      }

      if (finSelectedTickers.size === 0) {
        alert('Vui lòng chọn ít nhất 1 mã chứng khoán!');
        return;
      }

      const tickers = Array.from(finSelectedTickers);
      const startYear = parseInt(document.getElementById('finYearFrom').value) || 2014;
      const endYear = parseInt(document.getElementById('finYearTo').value) || 2024;
      const itemCodes = Array.from(finSelectedItems.keys());
      const ratios = [];
      document.querySelectorAll('.fin-ratio-chk').forEach(lbl => {
        if (lbl.style.display !== 'none') {
          const chk = lbl.querySelector('input[type="checkbox"]:checked');
          if (chk) ratios.push(chk.value);
        }
      });
      const exchange = document.getElementById('finExchangeSelect').value || null;
      const dropEmpty = document.getElementById('finDropEmpty') ? document.getElementById('finDropEmpty').checked : true;

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
        const body = { tickers, start_year: startYear, end_year: endYear, item_codes: itemCodes, ratios, drop_empty: dropEmpty };
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
        btnFinQuery.textContent = 'Tải Dữ Liệu BCTC';
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

    let summaryText = `${data.total_rows} quan sát (${data.total_tickers} mã x ${data.year_range[0]}-${data.year_range[1]}) | ${data.columns.length} biến`;
    if (data.missing_tickers && data.missing_tickers.length > 0) {
      summaryText += ` | ⚠️ Đã tự động bỏ qua ${data.missing_tickers.length} mã không có trong CSDL: ${data.missing_tickers.join(', ')}`;
    }
    summary.textContent = summaryText;

    document.getElementById('finDlCsv').href = data.csv_download;
    document.getElementById('finDlXlsx').href = data.xlsx_download;
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

  // --------------------------------------------------------------------------
  // 5. News Mining Tab (Multi-Source News Aggregator & Text Mining)
  // --------------------------------------------------------------------------
  function initNewsTab() {
    let lastNewsResult = null;
    let currentPreviewArticles = [];

    const newsTickerInput = document.getElementById('newsTickerInput');
    const newsTickerCounter = document.getElementById('newsTickerCounter');
    const newsTickerPills = document.getElementById('newsTickerPills');
    const newsSectorL1 = document.getElementById('newsSectorL1');
    const newsSectorL2 = document.getElementById('newsSectorL2');
    const btnNewsAddSector = document.getElementById('btnNewsAddSector');
    const btnClearNewsTickers = document.getElementById('btnClearNewsTickers');
    const quickGroupBtns = document.querySelectorAll('.news-quick-group');

    const newsYearFrom = document.getElementById('newsYearFrom');
    const newsYearTo = document.getElementById('newsYearTo');

    const srcCompanyWeb = document.getElementById('srcCompanyWeb');
    const srcCafeF = document.getElementById('srcCafeF');
    const srcVnExpress = document.getElementById('srcVnExpress');
    const srcCafeBiz = document.getElementById('srcCafeBiz');
    const srcTinNhanhCK = document.getElementById('srcTinNhanhCK');
    const srcVnEconomy = document.getElementById('srcVnEconomy');
    const srcVietnamNet = document.getElementById('srcVietnamNet');
    const srcCustomUrls = document.getElementById('srcCustomUrls');
    const customUrlsContainer = document.getElementById('customUrlsContainer');
    const customUrlsInput = document.getElementById('customUrlsInput');

    const newsTargetArticles = document.getElementById('newsTargetArticles');
    const newsTopicSelect = document.getElementById('newsTopicSelect');

    const btnExecuteNewsMining = document.getElementById('btnExecuteNewsMining');
    const btnOnlyScrapeNews = document.getElementById('btnOnlyScrapeNews');
    const btnOpenCompanyDirectory = document.getElementById('btnOpenCompanyDirectory');
    const btnCloseCompanyModal = document.getElementById('btnCloseCompanyModal');
    const companyDirectoryModal = document.getElementById('companyDirectoryModal');

    const newsProgressCard = document.getElementById('newsProgressCard');
    const newsProgressPhase = document.getElementById('newsProgressPhase');
    const newsProgressPercent = document.getElementById('newsProgressPercent');
    const newsProgressBarFill = document.getElementById('newsProgressBarFill');
    const newsProgressMessage = document.getElementById('newsProgressMessage');

    const newsPreviewCard = document.getElementById('newsPreviewCard');
    const newsPreviewTableBody = document.getElementById('newsPreviewTableBody');
    const previewArticleCount = document.getElementById('previewArticleCount');
    const btnMineFromPreview = document.getElementById('btnMineFromPreview');

    const newsResultsCard = document.getElementById('newsResultsCard');
    const newsStatArticlesCount = document.getElementById('newsStatArticlesCount');
    const newsStatFirmsHitCount = document.getElementById('newsStatFirmsHitCount');
    const newsStatMentionsCount = document.getElementById('newsStatMentionsCount');
    const btnViewFirmSummary = document.getElementById('btnViewFirmSummary');
    const btnViewArticlePanel = document.getElementById('btnViewArticlePanel');
    const newsPanelThead = document.getElementById('newsPanelThead');
    const newsPanelTbody = document.getElementById('newsPanelTbody');
    const newsSnippetsContainer = document.getElementById('newsSnippetsContainer');

    const btnNewsDlExcel = document.getElementById('btnNewsDlExcel');
    const btnNewsDlStata = document.getElementById('btnNewsDlStata');
    const btnNewsDlCsv = document.getElementById('btnNewsDlCsv');
    const newsTabBadge = document.getElementById('newsTabBadge');

    // Fallback Paste
    const pasteTickerInput = document.getElementById('pasteTickerInput');
    const pasteTitleInput = document.getElementById('pasteTitleInput');
    const pasteNewsTextarea = document.getElementById('pasteNewsTextarea');
    const pasteTopicSelect = document.getElementById('pasteTopicSelect');
    const btnExecutePasteMining = document.getElementById('btnExecutePasteMining');
    const pasteResultSummary = document.getElementById('pasteResultSummary');

    // 1. Ticker Selection & Pills (Học tập tab BCTC: Enter để thêm mã, pills trực quan)
    let newsSectorTree = [];
    const newsSelectedTickers = new Set(['VCB', 'HPG', 'FPT', 'SSI', 'VNM']);
    let newsPillsExpanded = false;

    function renderNewsTickerPills() {
      if (!newsTickerPills) return;
      newsTickerPills.innerHTML = '';

      if (newsSelectedTickers.size === 0) {
        newsTickerPills.innerHTML = '<span class="fin-pills-placeholder">Chưa chọn mã nào. Nhập mã CK ở trên rồi nhấn Enter, hoặc chọn theo ngành</span>';
        if (newsTickerCounter) newsTickerCounter.textContent = '0 mã đã chọn';
        return;
      }

      const tickerArray = Array.from(newsSelectedTickers);
      if (newsTickerCounter) newsTickerCounter.textContent = `${tickerArray.length} mã đã chọn`;

      // Summary badge
      const countBadge = document.createElement('span');
      countBadge.style.cssText = 'font-size: 11px; font-weight: 700; color: var(--brand-primary); background: rgba(99,102,241,0.12); padding: 2px 8px; border-radius: 12px; margin-right: 4px;';
      countBadge.textContent = `${tickerArray.length} mã`;
      newsTickerPills.appendChild(countBadge);

      const maxVisible = newsPillsExpanded ? tickerArray.length : 30;
      const visibleTickers = tickerArray.slice(0, maxVisible);

      visibleTickers.forEach(ticker => {
        const pill = document.createElement('span');
        pill.className = 'fin-ticker-pill';
        pill.innerHTML = `${escapeHtml(ticker)} <span class="pill-remove" data-ticker="${ticker}">×</span>`;
        pill.querySelector('.pill-remove').addEventListener('click', () => {
          newsSelectedTickers.delete(ticker);
          renderNewsTickerPills();
        });
        newsTickerPills.appendChild(pill);
      });

      if (tickerArray.length > 30) {
        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'btn btn-secondary btn-sm';
        toggleBtn.style.cssText = 'font-size: 11px; padding: 2px 8px; border-radius: 12px; margin-left: 4px;';
        toggleBtn.textContent = newsPillsExpanded ? 'Thu gọn' : `Xem thêm ${tickerArray.length - 30} mã...`;
        toggleBtn.addEventListener('click', () => {
          newsPillsExpanded = !newsPillsExpanded;
          renderNewsTickerPills();
        });
        newsTickerPills.appendChild(toggleBtn);
      }
    }

    // Ticker input — Enter to add
    if (newsTickerInput) {
      newsTickerInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const val = newsTickerInput.value.trim();
          if (!val) return;
          const tickers = val.split(/[,;\s]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
          tickers.forEach(t => newsSelectedTickers.add(t));
          newsTickerInput.value = '';
          renderNewsTickerPills();
        }
      });
      newsTickerInput.addEventListener('blur', () => {
        const val = newsTickerInput.value.trim();
        if (val) {
          const tickers = val.split(/[,;\s]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
          tickers.forEach(t => newsSelectedTickers.add(t));
          newsTickerInput.value = '';
          renderNewsTickerPills();
        }
      });
    }

    // Initial render of default pills
    renderNewsTickerPills();

    // 1.1 Load sectors into news dropdowns
    async function loadNewsSectors() {
      try {
        const res = await fetch('/api/catalog/sectors');
        const data = await res.json();
        newsSectorTree = data.sectors || [];
        if (newsSectorL1) {
          newsSectorL1.innerHTML = '<option value="">Tất cả ngành (L1)</option>';
          newsSectorTree.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.name;
            opt.textContent = `${s.name} (${s.total_tickers} mã)`;
            newsSectorL1.appendChild(opt);
          });
        }
      } catch (e) {
        console.error('Lỗi tải ngành cho news tab:', e);
      }
    }
    loadNewsSectors();

    if (newsSectorL1) {
      newsSectorL1.addEventListener('change', () => {
        const selectedL1 = newsSectorL1.value;
        if (!newsSectorL2) return;
        newsSectorL2.innerHTML = '<option value="">Tất cả phân ngành (L2)</option>';
        if (selectedL1 && newsSectorTree) {
          const found = newsSectorTree.find(s => s.name === selectedL1);
          if (found && found.subsectors) {
            found.subsectors.forEach(sub => {
              const opt = document.createElement('option');
              opt.value = sub.name;
              opt.textContent = `${sub.name} (${(sub.tickers || []).length} mã)`;
              newsSectorL2.appendChild(opt);
            });
          }
        }
      });
    }

    if (btnNewsAddSector) {
      btnNewsAddSector.addEventListener('click', () => {
        const l1 = newsSectorL1 ? newsSectorL1.value : '';
        const l2 = newsSectorL2 ? newsSectorL2.value : '';
        if (!l1 && !l2) {
          alert('Vui lòng chọn Ngành hoặc Phân ngành trước khi thêm.');
          return;
        }
        if (!newsSectorTree || newsSectorTree.length === 0) {
          alert('Dữ liệu ngành đang được nạp, vui lòng thử lại sau giây lát.');
          return;
        }

        let tickersToAdd = [];
        if (l1) {
          const foundL1 = newsSectorTree.find(s => s.name === l1);
          if (foundL1) {
            if (l2) {
              const sub = (foundL1.subsectors || []).find(s => s.name === l2);
              if (sub && sub.tickers) tickersToAdd = sub.tickers;
            } else {
              (foundL1.subsectors || []).forEach(sub => {
                if (sub.tickers) tickersToAdd.push(...sub.tickers);
              });
            }
          }
        } else if (l2) {
          newsSectorTree.forEach(s => {
            const sub = (s.subsectors || []).find(sub => sub.name === l2);
            if (sub && sub.tickers) tickersToAdd.push(...sub.tickers);
          });
        }

        if (tickersToAdd.length === 0) {
          alert('Không tìm thấy mã nào trong ngành này.');
          return;
        }

        tickersToAdd.forEach(t => newsSelectedTickers.add(t.toUpperCase()));
        renderNewsTickerPills();
      });
    }

    quickGroupBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const group = btn.getAttribute('data-tickers');
        if (group) {
          const groupTickers = group.split(',').map(t => t.trim().toUpperCase()).filter(Boolean);
          groupTickers.forEach(t => newsSelectedTickers.add(t));
          renderNewsTickerPills();
        }
      });
    });

    if (btnClearNewsTickers) {
      btnClearNewsTickers.addEventListener('click', () => {
        newsSelectedTickers.clear();
        if (newsTickerInput) newsTickerInput.value = '';
        renderNewsTickerPills();
      });
    }

    function getEnteredTickers() {
      if (newsTickerInput && newsTickerInput.value.trim()) {
        const val = newsTickerInput.value.trim();
        const extra = val.split(/[,;\s]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
        extra.forEach(t => newsSelectedTickers.add(t));
        newsTickerInput.value = '';
        renderNewsTickerPills();
      }
      return Array.from(newsSelectedTickers);
    }

    // 2. Custom URLs toggle
    if (srcCustomUrls && customUrlsContainer) {
      srcCustomUrls.addEventListener('change', () => {
        customUrlsContainer.style.display = srcCustomUrls.checked ? 'block' : 'none';
      });
    }

    function getSelectedSources() {
      const s = [];
      if (srcCompanyWeb && srcCompanyWeb.checked) s.push('company_website');
      if (srcCafeF && srcCafeF.checked) s.push('cafef');
      if (srcVnExpress && srcVnExpress.checked) s.push('vnexpress');
      if (srcCafeBiz && srcCafeBiz.checked) s.push('cafebiz');
      if (srcTinNhanhCK && srcTinNhanhCK.checked) s.push('tinnhanhchungkhoan');
      if (srcVnEconomy && srcVnEconomy.checked) s.push('vneconomy');
      if (srcVietnamNet && srcVietnamNet.checked) s.push('vietnamnet');
      if (srcCustomUrls && srcCustomUrls.checked) s.push('custom');
      return s;
    }

    function getCustomUrlsList() {
      if (!customUrlsInput || !srcCustomUrls || !srcCustomUrls.checked) return [];
      return customUrlsInput.value.split('\n').map(u => u.trim()).filter(u => u.startsWith('http'));
    }

    // 3. Scrape Only Stream
    if (btnOnlyScrapeNews) {
      btnOnlyScrapeNews.addEventListener('click', async () => {
        const tickers = getEnteredTickers();
        const sources = getSelectedSources();
        const customUrls = getCustomUrlsList();

        if (tickers.length === 0 && customUrls.length === 0) {
          alert('Vui lòng nhập ít nhất một mã chứng khoán (hoặc URL tùy chỉnh).');
          return;
        }
        if (sources.length === 0) {
          alert('Vui lòng chọn ít nhất một nguồn tin tức.');
          return;
        }

        const targetPerTicker = parseInt(newsTargetArticles ? newsTargetArticles.value : '20') || 20;
        const yearFrom = newsYearFrom ? parseInt(newsYearFrom.value) || 2020 : 2020;
        const yearTo = newsYearTo ? parseInt(newsYearTo.value) || 2026 : 2026;

        btnOnlyScrapeNews.disabled = true;
        newsProgressCard.style.display = 'block';
        newsPreviewCard.style.display = 'none';
        newsResultsCard.style.display = 'none';

        newsProgressPhase.textContent = 'Khởi động crawler...';
        newsProgressBarFill.style.width = '5%';
        newsProgressPercent.textContent = '5%';
        newsProgressMessage.textContent = `Đang kết nối tới ${sources.length} nguồn tin tức (năm ${yearFrom}-${yearTo})...`;

        try {
          const resp = await fetch('/api/news/scrape-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              tickers: tickers,
              sources: sources,
              target_articles_per_ticker: targetPerTicker,
              year_from: yearFrom,
              year_to: yearTo,
              custom_urls: customUrls,
            }),
          });

          const reader = resp.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (let i = 0; i < lines.length; i++) {
              const line = lines[i].trim();
              if (line.startsWith('data:')) {
                const jsonStr = line.slice(5).trim();
                if (!jsonStr) continue;
                try {
                  const eventData = JSON.parse(jsonStr);
                  if (eventData.message) {
                    newsProgressMessage.textContent = eventData.message;
                    if (eventData.total_tickers) {
                      const pct = Math.round((eventData.current_ticker_idx / eventData.total_tickers) * 90);
                      newsProgressBarFill.style.width = `${pct}%`;
                      newsProgressPercent.textContent = `${pct}%`;
                    }
                  }
                  if (eventData.articles) {
                    newsProgressBarFill.style.width = '100%';
                    newsProgressPercent.textContent = '100%';
                    newsProgressPhase.textContent = 'Đã hoàn tất thu thập tin tức!';
                    currentPreviewArticles = eventData.articles;
                    renderPreviewTable(eventData.articles);
                  }
                } catch (e) {}
              }
            }
          }
        } catch (err) {
          alert(`Lỗi cào tin tức: ${err.message}`);
        } finally {
          btnOnlyScrapeNews.disabled = false;
        }
      });
    }

    function renderPreviewTable(articles) {
      if (!newsPreviewTableBody) return;
      newsPreviewTableBody.innerHTML = '';
      if (previewArticleCount) previewArticleCount.textContent = articles.length;

      if (!articles || articles.length === 0) {
        newsPreviewTableBody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">Không thu thập được bài viết nào phù hợp bộ lọc năm.</td></tr>';
        newsPreviewCard.style.display = 'block';
        return;
      }

      articles.forEach(a => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${escapeHtml(a.ticker)}</strong></td>
          <td class="tabular">${escapeHtml(a.year || '—')}</td>
          <td><span class="badge-source badge-official">${escapeHtml(a.news_source)}</span></td>
          <td>
            <div style="font-weight: 500; color: var(--text-primary); cursor: pointer;" title="${escapeHtml(a.snippet || '')}">${escapeHtml(a.title || 'Không có tiêu đề')}</div>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">${escapeHtml(a.snippet || '')}</div>
          </td>
          <td><span style="font-size: 12px; color: var(--text-secondary);">${escapeHtml(a.published_date || 'N/A')}</span></td>
          <td style="text-align: right;" class="tabular">${(a.word_count || 0).toLocaleString()}</td>
          <td style="text-align: center;"><a href="${escapeHtml(a.url || '#')}" target="_blank" style="color: var(--brand-primary); text-decoration: none;">↗ Xem</a></td>
        `;
        newsPreviewTableBody.appendChild(tr);
      });

      newsPreviewCard.style.display = 'block';
      newsPreviewCard.scrollIntoView({ behavior: 'smooth' });
    }

    // 4. Mine News Stream (Full Workflow)
    if (btnExecuteNewsMining) {
      btnExecuteNewsMining.addEventListener('click', () => triggerNewsMining());
    }
    if (btnMineFromPreview) {
      btnMineFromPreview.addEventListener('click', () => triggerNewsMining());
    }

    async function triggerNewsMining() {
      const tickers = getEnteredTickers();
      const sources = getSelectedSources();
      const customUrls = getCustomUrlsList();

      if (tickers.length === 0 && customUrls.length === 0) {
        alert('Vui lòng nhập ít nhất một mã chứng khoán (hoặc URL tùy chỉnh).');
        return;
      }
      if (sources.length === 0) {
        alert('Vui lòng chọn ít nhất một nguồn tin tức.');
        return;
      }

      const targetPerTicker = parseInt(newsTargetArticles ? newsTargetArticles.value : '20') || 20;
      const yearFrom = newsYearFrom ? parseInt(newsYearFrom.value) || 2020 : 2020;
      const yearTo = newsYearTo ? parseInt(newsYearTo.value) || 2026 : 2026;
      const topic = newsTopicSelect ? newsTopicSelect.value : 'blockchain';

      if (btnExecuteNewsMining) btnExecuteNewsMining.disabled = true;
      if (btnMineFromPreview) btnMineFromPreview.disabled = true;
      newsProgressCard.style.display = 'block';
      newsResultsCard.style.display = 'none';

      newsProgressPhase.textContent = 'Đang thu thập tin tức...';
      newsProgressBarFill.style.width = '10%';
      newsProgressPercent.textContent = '10%';
      newsProgressMessage.textContent = `Bắt đầu gom tin tức cho ${tickers.length} mã từ ${sources.length} nguồn (năm ${yearFrom}-${yearTo})...`;

      try {
        const resp = await fetch('/api/news/mine-stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tickers: tickers,
            sources: sources,
            target_articles_per_ticker: targetPerTicker,
            year_from: yearFrom,
            year_to: yearTo,
            custom_urls: customUrls,
            topic: topic,
            threshold: 85,
          }),
        });

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            if (line.startsWith('data:')) {
              const jsonStr = line.slice(5).trim();
              if (!jsonStr) continue;
              try {
                const eventData = JSON.parse(jsonStr);
                if (eventData.detail) {
                  throw new Error(eventData.detail);
                }
                if (eventData.phase === 'crawl') {
                  const pct = Math.round((eventData.current / eventData.total) * 45);
                  newsProgressBarFill.style.width = `${pct}%`;
                  newsProgressPercent.textContent = `${pct}%`;
                  newsProgressPhase.textContent = 'Giai đoạn 1: Thu thập tin tức đa nguồn';
                  newsProgressMessage.textContent = eventData.message || '';
                } else if (eventData.phase === 'mining') {
                  const pct = 45 + Math.round((eventData.current / (eventData.total || 1)) * 50);
                  newsProgressBarFill.style.width = `${pct}%`;
                  newsProgressPercent.textContent = `${pct}%`;
                  newsProgressPhase.textContent = 'Giai đoạn 2: Khai phá văn bản theo từ điển';
                  newsProgressMessage.textContent = eventData.message || '';
                }

                if (eventData.firm_rows) {
                  newsProgressBarFill.style.width = '100%';
                  newsProgressPercent.textContent = '100%';
                  newsProgressPhase.textContent = 'Hoàn tất khai phá tin tức!';
                  lastNewsResult = eventData;
                  renderNewsResults(eventData);
                }
              } catch (e) {
                if (e.message && !e.message.includes('JSON')) throw e;
              }
            }
          }
        }
      } catch (err) {
        alert(`Lỗi khai phá tin tức: ${err.message}`);
      } finally {
        if (btnExecuteNewsMining) btnExecuteNewsMining.disabled = false;
        if (btnMineFromPreview) btnMineFromPreview.disabled = false;
      }
    }

    function renderNewsResults(data) {
      if (!newsResultsCard) return;

      const newsStatObsCount = document.getElementById('newsStatObsCount');
      if (newsStatObsCount) newsStatObsCount.textContent = (data.total_obs || (data.firm_rows ? data.firm_rows.length : 0)).toLocaleString();
      if (newsStatArticlesCount) newsStatArticlesCount.textContent = (data.total_articles || 0).toLocaleString();
      if (newsStatFirmsHitCount) newsStatFirmsHitCount.textContent = `${data.firms_with_hits || 0} / ${data.total_firms || 0}`;
      if (newsStatMentionsCount) newsStatMentionsCount.textContent = (data.total_mentions || 0).toLocaleString();

      if (btnNewsDlExcel) btnNewsDlExcel.href = data.excel_download || '#';
      if (btnNewsDlCsv) btnNewsDlCsv.href = data.csv_download || '#';
      if (btnNewsDlStata) btnNewsDlStata.href = data.dta_download || '#';

      if (newsTabBadge) {
        newsTabBadge.textContent = data.total_articles || 0;
        newsTabBadge.style.display = 'inline-flex';
      }

      renderFirmSummaryTable(data.firm_rows || []);
      renderNewsSnippets(data.snippets || []);

      newsResultsCard.style.display = 'block';
      newsResultsCard.scrollIntoView({ behavior: 'smooth' });
    }

    function renderFirmSummaryTable(rows) {
      if (!newsPanelThead || !newsPanelTbody) return;
      newsPanelThead.innerHTML = `
        <tr>
          <th style="width: 75px;">Mã CK</th>
          <th style="width: 60px; text-align: center;">Năm</th>
          <th style="width: 80px; text-align: right;" title="Số lượng bài báo thu thập được trong năm">Số Bài</th>
          <th style="width: 85px; text-align: right;" title="Số bài báo có chứa ít nhất 1 từ khóa">Bài Có Hits</th>
          <th style="width: 90px; text-align: right;" title="Tổng số từ của các bài báo trong năm">Tổng Số Từ</th>
          <th style="width: 95px; text-align: right; color: var(--color-success);" class="th-hint" title="Frequency / Hits: Tổng số lần xuất hiện từ khóa trong năm (Wu et al. 2021)">Frequency</th>
          <th style="width: 105px; text-align: right; color: #60a5fa;" class="th-hint" title="Biến chính mô hình: ln(1 + Frequency) (Wu et al. 2021, MDPI 2026)">Log (Main)</th>
          <th style="width: 75px; text-align: center;" class="th-hint" title="Mention: Biến giả 1 nếu Frequency > 0, ngược lại 0 (Baier et al. 2020)">Mention</th>
          <th style="width: 95px; text-align: right;" class="th-hint" title="Mật độ từ khóa trên 1.000 từ">Mật Độ (/1k)</th>
        </tr>
      `;

      newsPanelTbody.innerHTML = '';
      if (!rows || rows.length === 0) {
        newsPanelTbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">Không có dữ liệu bảng (Firm-Year).</td></tr>';
        return;
      }

      rows.forEach(r => {
        const tr = document.createElement('tr');
        const hits = r.total_mentions || 0;
        const logFreq = typeof r.log_frequency === 'number' ? r.log_frequency.toFixed(4) : (r.log_frequency || '0.0000');
        const mention = r.mention !== undefined ? r.mention : (hits > 0 ? 1 : 0);
        const density = typeof r.keyword_density_per_1k === 'number' ? r.keyword_density_per_1k.toFixed(4) : (r.keyword_density_per_1k || '0');

        tr.innerHTML = `
          <td><strong style="color: var(--text-primary); font-family: var(--font-mono);">${escapeHtml(r.ticker)}</strong></td>
          <td class="tabular" style="text-align: center; font-weight: 500;">${r.year || '—'}</td>
          <td style="text-align: right;" class="tabular">${(r.total_articles || 0).toLocaleString()}</td>
          <td style="text-align: right;" class="tabular" style="color: ${r.articles_with_hits > 0 ? 'var(--color-success)' : 'inherit'}; font-weight: ${r.articles_with_hits > 0 ? '600' : 'normal'};">${(r.articles_with_hits || 0).toLocaleString()}</td>
          <td style="text-align: right;" class="tabular">${(r.total_words || 0).toLocaleString()}</td>
          <td style="text-align: right;" class="tabular" style="color: ${hits > 0 ? 'var(--color-success)' : 'inherit'}; font-weight: 700;">${hits.toLocaleString()}</td>
          <td style="text-align: right; color: #3b82f6; font-weight: 700;" class="tabular">${logFreq}</td>
          <td style="text-align: center;">${mention > 0 ? '<span style="color: var(--color-success); font-weight: 700;">1</span>' : '<span style="color: var(--text-muted);">0</span>'}</td>
          <td style="text-align: right;" class="tabular">${density}</td>
        `;
        newsPanelTbody.appendChild(tr);
      });
    }

    function renderArticlePanelTable(rows) {
      if (!newsPanelThead || !newsPanelTbody) return;
      newsPanelThead.innerHTML = `
        <tr>
          <th style="width: 70px;">Mã CK</th>
          <th style="width: 55px;">Năm</th>
          <th style="width: 110px;">Nguồn</th>
          <th>Tiêu Đề Bài Báo</th>
          <th style="width: 85px;">Ngày</th>
          <th style="width: 70px; text-align: right;">Số Từ</th>
          <th style="width: 80px; text-align: right; color: #60a5fa;">Hits</th>
          <th style="width: 60px; text-align: center;">Link</th>
        </tr>
      `;

      newsPanelTbody.innerHTML = '';
      if (!rows || rows.length === 0) {
        newsPanelTbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 30px;">Không có dữ liệu bài viết.</td></tr>';
        return;
      }

      rows.forEach(r => {
        const freq = r.frequency || r.Frequency || r.hits || 0;
        const yr = r.year || r.published_year || '';
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${escapeHtml(r.ticker)}</strong></td>
          <td class="tabular">${escapeHtml(yr || '—')}</td>
          <td><span class="badge-source badge-official">${escapeHtml(r.news_source || '')}</span></td>
          <td><div style="font-weight: 500;">${escapeHtml(r.title || '')}</div></td>
          <td><span style="font-size: 11px; color: var(--text-secondary);">${escapeHtml(r.published_date || 'N/A')}</span></td>
          <td style="text-align: right;" class="tabular">${(r.word_count || 0).toLocaleString()}</td>
          <td style="text-align: right;" class="tabular" style="color: ${freq > 0 ? '#60a5fa' : 'inherit'}; font-weight: ${freq > 0 ? '600' : 'normal'};">${freq}</td>
          <td style="text-align: center;"><a href="${escapeHtml(r.url || '#')}" target="_blank" style="color: var(--brand-primary); text-decoration: none;">↗</a></td>
        `;
        newsPanelTbody.appendChild(tr);
      });
    }

    if (btnViewFirmSummary && btnViewArticlePanel) {
      btnViewFirmSummary.addEventListener('click', () => {
        btnViewFirmSummary.classList.add('active');
        btnViewArticlePanel.classList.remove('active');
        if (lastNewsResult) renderFirmSummaryTable(lastNewsResult.firm_rows || []);
      });

      btnViewArticlePanel.addEventListener('click', () => {
        btnViewArticlePanel.classList.add('active');
        btnViewFirmSummary.classList.remove('active');
        if (lastNewsResult) renderArticlePanelTable(lastNewsResult.article_rows || []);
      });
    }

    function renderNewsSnippets(snippets) {
      if (!newsSnippetsContainer) return;
      newsSnippetsContainer.innerHTML = '';
      if (!snippets || snippets.length === 0) {
        newsSnippetsContainer.innerHTML = '<p style="color: var(--text-muted); font-style: italic;">Không tìm thấy trích đoạn từ khóa nào.</p>';
        return;
      }

      snippets.forEach(s => {
        const div = document.createElement('div');
        div.className = 'news-snippet-item';
        const ctxHtml = escapeHtml(s.context).replace(
          new RegExp(escapeRegExp(s.keyword), 'gi'),
          '<mark>$&</mark>'
        );
        div.innerHTML = `
          <div style="display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 11px; color: var(--text-muted);">
            <span><strong>${escapeHtml(s.ticker)}</strong> | ${escapeHtml(s.source || '')} | Từ khóa: <code style="color: var(--brand-primary);">${escapeHtml(s.keyword)}</code></span>
            <a href="${escapeHtml(s.url || '#')}" target="_blank" style="color: var(--brand-primary); text-decoration: none;">Xem bài viết ↗</a>
          </div>
          <div style="color: var(--text-secondary);">${ctxHtml}</div>
        `;
        newsSnippetsContainer.appendChild(div);
      });
    }

    // 6. Fallback Paste Text Mining
    if (btnExecutePasteMining) {
      btnExecutePasteMining.addEventListener('click', async () => {
        const text = pasteNewsTextarea ? pasteNewsTextarea.value.trim() : '';
        if (!text) {
          alert('Vui lòng dán văn bản bài báo vào ô trước khi bấm khai phá.');
          return;
        }

        btnExecutePasteMining.disabled = true;
        btnExecutePasteMining.textContent = 'Đang khai phá...';

        try {
          const resp = await fetch('/api/news/mine-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              ticker: pasteTickerInput ? pasteTickerInput.value.trim().toUpperCase() || 'CUSTOM' : 'CUSTOM',
              title: pasteTitleInput ? pasteTitleInput.value.trim() || 'Văn bản nhập thủ công' : 'Văn bản nhập thủ công',
              text: text,
              topic: pasteTopicSelect ? pasteTopicSelect.value : 'blockchain',
              threshold: 85,
            }),
          });

          if (!resp.ok) throw new Error('Lỗi khai phá văn bản');
          const res = await resp.json();

          if (pasteResultSummary) {
            pasteResultSummary.innerHTML = `
              <div style="padding: 10px; background: var(--bg-surface); border: 1px solid var(--border-default); border-radius: 6px; margin-top: 8px;">
                <div style="font-weight: 600; color: var(--brand-primary); margin-bottom: 4px;">Kết quả khai phá: ${escapeHtml(res.ticker)}</div>
                <div>Tổng số từ: <strong>${res.total_words.toLocaleString()}</strong> | Lượt xuất hiện (Hits): <strong style="color: #60a5fa;">${res.total_hits}</strong></div>
                <div style="margin-top: 6px; font-size: 11px; color: var(--text-muted);">
                  ${res.snippets.length > 0 ? res.snippets.map(s => `<div>• <code>${escapeHtml(s.keyword)}</code>: ...${escapeHtml(s.context)}...</div>`).join('') : 'Không xuất hiện từ khóa nào trong từ điển.'}
                </div>
              </div>
            `;
          }
        } catch (err) {
          alert(`Lỗi: ${err.message}`);
        } finally {
          btnExecutePasteMining.disabled = false;
          btnExecutePasteMining.textContent = 'Khai Phá Văn Bản Đã Dán';
        }
      });
    }

    // 7. Company Websites Directory Modal
    const dirSearchInput = document.getElementById('dirSearchInput');
    const dirExchangeSelect = document.getElementById('dirExchangeSelect');
    const dirHasWebOnly = document.getElementById('dirHasWebOnly');
    const companyDirectoryTbody = document.getElementById('companyDirectoryTbody');

    if (btnOpenCompanyDirectory && companyDirectoryModal) {
      btnOpenCompanyDirectory.addEventListener('click', () => {
        companyDirectoryModal.style.display = 'flex';
        loadCompanyDirectory();
      });
    }

    if (btnCloseCompanyModal && companyDirectoryModal) {
      btnCloseCompanyModal.addEventListener('click', () => {
        companyDirectoryModal.style.display = 'none';
      });
    }

    async function loadCompanyDirectory() {
      if (!companyDirectoryTbody) return;
      companyDirectoryTbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">Đang tải danh bạ website...</td></tr>';

      const q = dirSearchInput ? dirSearchInput.value : '';
      const ex = dirExchangeSelect ? dirExchangeSelect.value : '';
      const hasWeb = dirHasWebOnly ? dirHasWebOnly.checked : false;

      try {
        const res = await fetch(`/api/news/companies?query=${encodeURIComponent(q)}&exchange=${encodeURIComponent(ex)}&has_website_only=${hasWeb}&limit=150`);
        const data = await res.json();
        renderCompanyDirectoryTable(data.companies || []);
      } catch (err) {
        companyDirectoryTbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--color-danger); padding: 20px;">Lỗi: ${err.message}</td></tr>`;
      }
    }

    if (dirSearchInput) {
      let debounceTimer;
      dirSearchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(loadCompanyDirectory, 250);
      });
    }
    if (dirExchangeSelect) dirExchangeSelect.addEventListener('change', loadCompanyDirectory);
    if (dirHasWebOnly) dirHasWebOnly.addEventListener('change', loadCompanyDirectory);

    function renderCompanyDirectoryTable(companies) {
      if (!companyDirectoryTbody) return;
      companyDirectoryTbody.innerHTML = '';
      if (!companies || companies.length === 0) {
        companyDirectoryTbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">Không tìm thấy doanh nghiệp nào.</td></tr>';
        return;
      }

      companies.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${escapeHtml(c.ticker)}</strong></td>
          <td><span class="badge-source badge-official">${escapeHtml(c.exchange || 'HOSE/HNX')}</span></td>
          <td>${escapeHtml(c.name || '')}</td>
          <td>${c.website ? `<a href="${escapeHtml(c.website)}" target="_blank" style="color: var(--brand-primary);">${escapeHtml(c.website)}</a>` : '<span style="color: var(--text-muted); font-style: italic;">Auto-Discovery</span>'}</td>
          <td>${c.ir_portal ? `<a href="${escapeHtml(c.ir_portal)}" target="_blank" style="color: var(--text-secondary);">Cổng IR ↗</a>` : '<span style="color: var(--text-muted);">-</span>'}</td>
          <td style="text-align: center;">
            <button class="btn btn-secondary btn-sm btn-edit-company-web" data-ticker="${escapeHtml(c.ticker)}" data-web="${escapeHtml(c.website || '')}">Sửa</button>
          </td>
        `;
        companyDirectoryTbody.appendChild(tr);
      });

      // Add edit listeners
      companyDirectoryTbody.querySelectorAll('.btn-edit-company-web').forEach(b => {
        b.addEventListener('click', async () => {
          const t = b.getAttribute('data-ticker');
          const currentWeb = b.getAttribute('data-web');
          const newWeb = prompt(`Nhập URL website cho mã ${t}:`, currentWeb);
          if (newWeb !== null) {
            try {
              const res = await fetch('/api/news/companies/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ticker: t, website: newWeb.trim() }),
              });
              if (res.ok) {
                alert(`Đã cập nhật website cho ${t}!`);
                loadCompanyDirectory();
              }
            } catch (err) {
              alert(`Lỗi: ${err.message}`);
            }
          }
        });
      });
    }
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
  initNewsTab();
});

