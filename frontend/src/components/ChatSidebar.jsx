import React from 'react';
import { MessageSquare, Plus, Trash2, PanelLeftClose, PanelLeftOpen, Clock } from 'lucide-react';

export default function ChatSidebar({
  sessions = [],
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  collapsed = false,
  onToggleCollapse,
}) {
  return (
    <aside className={`chat-sidebar ${collapsed ? 'collapsed' : ''}`}>
      {/* Top Header Controls */}
      <div className="sidebar-header">
        {!collapsed && (
          <div className="sidebar-title">
            <MessageSquare size={16} color="var(--accent-primary)" />
            <span>SAVED CHATS</span>
          </div>
        )}
        <div className="sidebar-header-actions">
          <button
            type="button"
            className="sidebar-icon-btn"
            onClick={onToggleCollapse}
            title={collapsed ? 'Expand Chat History' : 'Collapse Sidebar'}
          >
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
        </div>
      </div>

      {/* New Chat Button */}
      <div className="new-chat-wrapper">
        <button
          type="button"
          className="new-chat-btn"
          onClick={onNewChat}
          title="Start New Chat Session"
        >
          <Plus size={16} />
          {!collapsed && <span>New Chat</span>}
        </button>
      </div>

      {/* Scrollable Saved Sessions Feed */}
      <div className="sidebar-feed">
        {!collapsed && sessions.length === 0 ? (
          <div className="sidebar-empty">
            <p>No saved chat sessions yet.</p>
            <span className="sub-text">Consented chats will be saved here automatically.</span>
          </div>
        ) : (
          sessions.map((sess) => {
            const isActive = sess.session_id === activeSessionId;
            return (
              <div
                key={sess.session_id}
                className={`session-item ${isActive ? 'active' : ''}`}
                onClick={() => onSelectSession(sess.session_id)}
                title={sess.title}
              >
                <div className="session-item-icon">
                  <MessageSquare size={14} color={isActive ? 'var(--accent-primary)' : 'var(--text-muted)'} />
                </div>

                {!collapsed && (
                  <div className="session-item-content">
                    <span className="session-item-title">{sess.title}</span>
                    <div className="session-item-meta">
                      <Clock size={10} />
                      <span>
                        {sess.created_at ? new Date(sess.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' }) : 'Recent'}
                      </span>
                      <span className="count-pill">{sess.message_count} msgs</span>
                    </div>
                  </div>
                )}

                {!collapsed && (
                  <button
                    type="button"
                    className="session-delete-btn"
                    title="Delete Chat Session"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(sess.session_id);
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
