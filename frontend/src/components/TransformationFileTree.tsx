"use client";

import React, { useMemo, useRef, useState, useCallback } from "react";

interface ChangedFileEntry {
  file_path: string;
  change_type: string;
  classification: string;
  lines_added: number;
  lines_removed: number;
  is_generated?: boolean;
  is_binary?: boolean;
  evidence_mode?: string;
  unsupported_reason?: string;
}

interface Props {
  files: ChangedFileEntry[];
  selectedFile: string | null;
  onSelectFile: (filePath: string | null) => void;
  searchQuery?: string;
  filterClassification?: string;
  filterChangeType?: string;
}

interface TreeNode {
  name: string;
  path: string;
  depth: number;
  children: TreeNode[];
  files: ChangedFileEntry[];
}

const CLASSIFICATION_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high_risk: "bg-orange-100 text-orange-700 border-orange-200",
  high: "bg-orange-100 text-orange-700 border-orange-200",
  medium_risk: "bg-amber-100 text-amber-700 border-amber-200",
  medium: "bg-amber-100 text-amber-700 border-amber-200",
  low_risk: "bg-green-100 text-green-700 border-green-200",
  low: "bg-green-100 text-green-700 border-green-200",
  sensitive: "bg-red-100 text-red-700 border-red-200",
  generated: "bg-gray-100 text-gray-600 border-gray-200",
  unknown: "bg-yellow-100 text-yellow-700 border-yellow-200",
};

const DOT_COLORS: Record<string, string> = {
  critical: "bg-red-500",
  high_risk: "bg-orange-500",
  high: "bg-orange-500",
  medium_risk: "bg-amber-500",
  medium: "bg-amber-500",
  low_risk: "bg-green-500",
  low: "bg-green-500",
  sensitive: "bg-red-500",
  generated: "bg-gray-400",
  unknown: "bg-yellow-500",
};

function isCriticalOrHigh(classification: string): boolean {
  return classification === "critical" || classification === "high_risk" || classification === "high" || classification === "sensitive";
}

function buildTree(files: ChangedFileEntry[]): TreeNode {
  const root: TreeNode = { name: "/", path: "", depth: 0, children: [], files: [] };

  for (const file of files) {
    const parts = file.file_path.split("/");
    let current = root;

    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      let child = current.children.find((c) => c.name === part);
      if (!child) {
        child = {
          name: part,
          path: parts.slice(0, i + 1).join("/"),
          depth: i + 1,
          children: [],
          files: [],
        };
        current.children.push(child);
      }
      current = child;
    }

    current.files.push(file);
  }

  return root;
}

export function TransformationFileTree(props: Props) {
  const { files, selectedFile, onSelectFile, searchQuery = "", filterClassification = "", filterChangeType = "" } = props;
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    files.forEach((f) => {
      const parts = f.file_path.split("/");
      for (let i = 1; i < parts.length; i++) {
        initial.add(parts.slice(0, i).join("/"));
      }
    });
    return initial;
  });
  const treeRef = useRef<HTMLDivElement>(null);
  const [localSearch, setLocalSearch] = useState("");

  const effectiveSearch = searchQuery || localSearch;

  const criticalFiles = useMemo(
    () => files.filter((f) => isCriticalOrHigh(f.classification)),
    [files],
  );

  const otherFiles = useMemo(
    () => files.filter((f) => !isCriticalOrHigh(f.classification)),
    [files],
  );

  const filteredOtherFiles = useMemo(() => {
    let result = otherFiles;

    if (effectiveSearch) {
      const q = effectiveSearch.toLowerCase();
      result = result.filter((f) => f.file_path.toLowerCase().includes(q));
    }

    if (filterClassification) {
      result = result.filter((f) => f.classification === filterClassification);
    }

    if (filterChangeType) {
      result = result.filter((f) => f.change_type === filterChangeType);
    }

    return result;
  }, [otherFiles, effectiveSearch, filterClassification, filterChangeType]);

  const criticalTree = useMemo(() => buildTree(criticalFiles), [criticalFiles]);
  const otherTree = useMemo(() => buildTree(filteredOtherFiles), [filteredOtherFiles]);

  const toggleDir = useCallback((path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const handleFileSelect = useCallback(
    (filePath: string) => {
      onSelectFile(selectedFile === filePath ? null : filePath);
    },
    [onSelectFile, selectedFile],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, type: "dir" | "file", path: string) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (type === "dir") {
          toggleDir(path);
        } else {
          handleFileSelect(path);
        }
      }
    },
    [toggleDir, handleFileSelect],
  );

  const renderFileRow = useCallback(
    (file: ChangedFileEntry, depth: number) => {
      const isSelected = selectedFile === file.file_path;
      const cls = file.classification;
      const badgeColor = CLASSIFICATION_COLORS[cls] || "bg-gray-100 text-gray-600 border-gray-200";
      const dotColor = DOT_COLORS[cls] || "bg-gray-400";
      const hasUnsupportedReason = file.evidence_mode && file.evidence_mode !== "full_diff" && file.unsupported_reason;

      return (
        <div
          key={file.file_path}
          role="treeitem"
          aria-selected={isSelected}
          tabIndex={0}
          onClick={() => handleFileSelect(file.file_path)}
          onKeyDown={(e) => handleKeyDown(e, "file", file.file_path)}
          className={`flex items-center gap-2 py-1 px-2 text-sm cursor-pointer rounded transition-colors ${
            isSelected
              ? "bg-blue-100 text-blue-900"
              : "hover:bg-gray-100 text-gray-800"
          }`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${dotColor}`} />
          <span className="truncate font-mono text-xs flex-1">{file.file_path.split("/").pop()}</span>
          {file.is_binary && (
            <span className="px-1 py-0.5 text-[10px] rounded bg-purple-100 text-purple-700 border border-purple-200 font-medium whitespace-nowrap">
              binary
            </span>
          )}
          {file.is_generated && (
            <span className="px-1 py-0.5 text-[10px] rounded bg-gray-100 text-gray-500 border border-gray-200 font-medium whitespace-nowrap">
              generated
            </span>
          )}
          {hasUnsupportedReason && file.unsupported_reason && (
            <span
              className="px-1 py-0.5 text-[10px] rounded bg-yellow-100 text-yellow-700 border border-yellow-200 font-medium whitespace-nowrap"
              title={file.unsupported_reason}
            >
              {file.unsupported_reason.length > 20
                ? file.unsupported_reason.slice(0, 18) + "…"
                : file.unsupported_reason}
            </span>
          )}
          <span className="text-green-600 text-xs font-medium tabular-nums">+{file.lines_added}</span>
          <span className="text-red-600 text-xs font-medium tabular-nums">-{file.lines_removed}</span>
          <span className={`px-1.5 py-0.5 text-[10px] rounded border font-medium whitespace-nowrap ${badgeColor}`}>
            {cls}
          </span>
        </div>
      );
    },
    [selectedFile, handleFileSelect, handleKeyDown],
  );

  const renderNode = useCallback(
    (node: TreeNode, depth: number, isPinned: boolean): React.ReactNode => {
      if (depth === 0) {
        return (
          <>
            {node.children.map((child) => renderNode(child, 1, isPinned))}
            {node.files.map((file) => renderFileRow(file, 0))}
          </>
        );
      }

      const isExpanded = expandedDirs.has(node.path);
      const hasFiles = node.files.length > 0;
      const hasChildDirs = node.children.length > 0;
      const isEmpty = !hasFiles && !hasChildDirs;

      if (isEmpty) return null;

      const showChildren = (hasFiles || hasChildDirs) && (isPinned || isExpanded);
      const fileCount = node.files.length;
      const childCount = node.children.length;

      return (
        <div key={node.path} role="none">
          {(childCount > 0 || fileCount > 0) && depth > 0 && (
            <div
              role="none"
              style={{ paddingLeft: `${(depth - 1) * 16 + 8}px` }}
            >
              <button
                role="treeitem"
                aria-expanded={isPinned ? true : isExpanded}
                tabIndex={0}
                onClick={() => toggleDir(node.path)}
                onKeyDown={(e) => handleKeyDown(e, "dir", node.path)}
                className="flex items-center gap-1.5 w-full text-left py-1 px-2 text-sm rounded hover:bg-gray-100 transition-colors text-gray-700 font-medium"
              >
                <svg
                  className={`w-3.5 h-3.5 flex-shrink-0 transition-transform text-gray-500 ${
                    (isPinned || isExpanded) ? "rotate-90" : ""
                  }`}
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
                    clipRule="evenodd"
                  />
                </svg>
                <svg className="w-4 h-4 flex-shrink-0 text-amber-500" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path d="M3.25 2A2.25 2.25 0 001 4.25v11.5A2.25 2.25 0 003.25 18h13.5A2.25 2.25 0 0019 15.75V7.25A2.25 2.25 0 0016.75 5h-5.836a.25.25 0 01-.177-.073L9.823 3.013A1.25 1.25 0 008.914 3H3.25z" />
                </svg>
                <span className="truncate">{node.name}</span>
                <span className="text-gray-400 text-xs ml-auto">
                  {fileCount > 0 && `${fileCount} file${fileCount !== 1 ? "s" : ""}`}
                  {fileCount > 0 && childCount > 0 && " · "}
                  {childCount > 0 && `${childCount} dir${childCount !== 1 ? "s" : ""}`}
                </span>
              </button>
            </div>
          )}
          {showChildren && (
            <div role="group">
              {node.children.map((child) => renderNode(child, depth + 1, isPinned))}
              {node.files.map((file) => renderFileRow(file, depth + (hasChildDirs ? 1 : 0)))}
            </div>
          )}
        </div>
      );
    },
    [expandedDirs, toggleDir, handleKeyDown, renderFileRow],
  );

  return (
    <div
      ref={treeRef}
      role="tree"
      aria-label="File tree"
      className="border border-gray-200 rounded-lg bg-white overflow-hidden"
    >
      <div className="p-2 border-b border-gray-200 space-y-2">
        <input
          type="text"
          value={localSearch}
          onChange={(e) => setLocalSearch(e.target.value)}
          placeholder="Search files…"
          aria-label="Search files"
          className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-blue-400"
        />
      </div>

      <div className="max-h-[500px] overflow-y-auto py-1">
        {criticalFiles.length > 0 && (
          <div role="group" aria-label="Critical and high-risk findings">
            <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-red-600 bg-red-50 border-b border-red-100 sticky top-0 z-10">
              Critical / High Risk — always visible ({criticalFiles.length})
            </div>
            {renderNode(criticalTree, 0, true)}
          </div>
        )}

        <div role="group" aria-label={criticalFiles.length > 0 ? "All other files" : "Files"}>
          {criticalFiles.length > 0 && (
            <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-500 bg-gray-50 border-b border-gray-100 sticky top-0 z-10">
              Other files ({filteredOtherFiles.length})
            </div>
          )}
          {filteredOtherFiles.length > 0 ? (
            renderNode(otherTree, 0, false)
          ) : (
            <div className="px-3 py-4 text-sm text-gray-400 text-center">
              {effectiveSearch || filterClassification || filterChangeType
                ? "No files match the current filters"
                : "No files to display"}
            </div>
          )}
        </div>
      </div>

      {effectiveSearch && filteredOtherFiles.length > 0 && (
        <div className="px-3 py-1.5 text-xs text-gray-500 border-t border-gray-200 bg-gray-50">
          {filteredOtherFiles.length} file{filteredOtherFiles.length !== 1 ? "s" : ""} match
        </div>
      )}
    </div>
  );
}
