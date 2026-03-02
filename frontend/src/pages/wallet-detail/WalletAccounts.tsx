import { useState } from "react";
import { Link } from "react-router-dom";
import {
  createAccount,
  updateAccount,
  deleteAccount,
  syncAccount,
  fetchWallets,
  type WalletDetail,
  type Account,
  type SyncResult,
  type WalletListItem,
} from "../../api/client";
import DropdownMenu from "../../components/DropdownMenu";

const BLOCKCHAINS = ["bitcoin", "ethereum", "solana", "cosmos", "litecoin"];

function detectBlockchain(address: string): string | null {
  const addr = address.trim();
  if (!addr) return null;
  if (addr.toLowerCase().startsWith("bc1") || ((addr[0] === "1" || addr[0] === "3") && addr.length >= 25 && addr.length <= 35)) return "bitcoin";
  if (addr.startsWith("0x") && addr.length === 42) return "ethereum";
  if (addr.toLowerCase().startsWith("cosmos1")) return "cosmos";
  if (addr.toLowerCase().startsWith("ltc1")) return "litecoin";
  if ((addr[0] === "L" || addr[0] === "M") && addr.length >= 26 && addr.length <= 35) return "litecoin";
  if (addr.length >= 32 && addr.length <= 44 && /^[1-9A-HJ-NP-Za-km-z]+$/.test(addr)) return "solana";
  return null;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

interface Props {
  wallet: WalletDetail;
  loadWallet: () => void;
  setError: (msg: string) => void;
}

export default function WalletAccounts({ wallet, loadWallet, setError }: Props) {
  const [showAccountForm, setShowAccountForm] = useState(false);
  const [acctName, setAcctName] = useState("");
  const [acctBlockchain, setAcctBlockchain] = useState("bitcoin");
  const [acctAddress, setAcctAddress] = useState("");
  const [acctCreating, setAcctCreating] = useState(false);
  const [syncingAccountId, setSyncingAccountId] = useState<number | null>(null);
  const [accountSyncResult, setAccountSyncResult] = useState<SyncResult | null>(null);
  const [renameAccountId, setRenameAccountId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [editAddressAccountId, setEditAddressAccountId] = useState<number | null>(null);
  const [editAddressValue, setEditAddressValue] = useState("");
  const [editBlockchainValue, setEditBlockchainValue] = useState("");
  const [moveAccountId, setMoveAccountId] = useState<number | null>(null);
  const [moveTargetWalletId, setMoveTargetWalletId] = useState<string>("");
  const [allWallets, setAllWallets] = useState<WalletListItem[]>([]);
  const [moveLoading, setMoveLoading] = useState(false);

  async function handleCreateAccount(e: React.FormEvent) {
    e.preventDefault();
    setAcctCreating(true);
    try {
      await createAccount(wallet.id, { name: acctName, address: acctAddress, blockchain: acctBlockchain });
      setShowAccountForm(false);
      setAcctName("");
      setAcctAddress("");
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to create account");
    } finally {
      setAcctCreating(false);
    }
  }

  async function handleSyncAccount(account: Account) {
    setSyncingAccountId(account.id);
    setAccountSyncResult(null);
    try {
      const resp = await syncAccount(wallet.id, account.id);
      setAccountSyncResult(resp.data);
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Sync failed");
    } finally {
      setSyncingAccountId(null);
    }
  }

  async function handleRenameAccount(account: Account) {
    try {
      await updateAccount(wallet.id, account.id, { name: renameValue });
      setRenameAccountId(null);
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Rename failed");
    }
  }

  async function handleSaveAddress(account: Account) {
    try {
      await updateAccount(wallet.id, account.id, {
        address: editAddressValue,
        blockchain: editBlockchainValue || undefined,
      });
      setEditAddressAccountId(null);
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to update address");
    }
  }

  async function handleArchiveAccount(account: Account) {
    try {
      await updateAccount(wallet.id, account.id, { is_archived: !account.is_archived });
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Archive failed");
    }
  }

  async function handleDeleteAccount(account: Account) {
    if (!confirm(`Delete account "${account.name}"?`)) return;
    try {
      await deleteAccount(wallet.id, account.id);
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Delete failed");
    }
  }

  function openMoveAccount(account: Account) {
    setMoveAccountId(account.id);
    setMoveTargetWalletId("");
    fetchWallets()
      .then((r) => setAllWallets(r.data.filter((w: WalletListItem) => w.id !== wallet.id && w.category === "wallet")))
      .catch(() => {});
  }

  async function handleMoveAccount() {
    if (!moveAccountId || !moveTargetWalletId) return;
    setMoveLoading(true);
    try {
      await updateAccount(wallet.id, moveAccountId, { wallet_id: Number(moveTargetWalletId) } as any);
      setMoveAccountId(null);
      loadWallet();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Move failed");
    } finally {
      setMoveLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>Blockchain Accounts</h2>
        <button
          onClick={() => setShowAccountForm(!showAccountForm)}
          className="text-xs px-2 py-1 text-white rounded transition-colors"
          style={{ backgroundColor: "var(--accent)" }}
        >
          {showAccountForm ? "Cancel" : "Add Account"}
        </button>
      </div>

      {showAccountForm && (
        <form onSubmit={handleCreateAccount} className="glass-card p-3 space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="text-xs block" style={{ color: "var(--text-muted)" }}>Name</label>
              <input value={acctName} onChange={(e) => setAcctName(e.target.value)} required placeholder="My BTC" className="rounded px-2 py-1 text-sm w-full" />
            </div>
            <div>
              <label className="text-xs block" style={{ color: "var(--text-muted)" }}>Blockchain</label>
              <select value={acctBlockchain} onChange={(e) => setAcctBlockchain(e.target.value)} className="rounded px-2 py-1 text-sm w-full">
                {BLOCKCHAINS.map((b) => <option key={b} value={b}>{b.charAt(0).toUpperCase() + b.slice(1)}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs block" style={{ color: "var(--text-muted)" }}>Address</label>
              <input
                value={acctAddress}
                onChange={(e) => {
                  setAcctAddress(e.target.value);
                  const detected = detectBlockchain(e.target.value);
                  if (detected) setAcctBlockchain(detected);
                }}
                required placeholder="bc1q..." className="rounded px-2 py-1 text-sm w-full"
              />
            </div>
          </div>
          <button type="submit" disabled={acctCreating} className="px-3 py-1 text-white rounded text-xs disabled:opacity-50 transition-colors" style={{ backgroundColor: "var(--success)" }}>
            {acctCreating ? "Adding..." : "Add Account"}
          </button>
        </form>
      )}

      {wallet.accounts.length === 0 ? (
        <div className="text-sm py-4 text-center" style={{ color: "var(--text-muted)" }}>
          No accounts yet. Add a blockchain address to get started.
        </div>
      ) : (
        <div className="space-y-2">
          {wallet.accounts.map((acct) => (
            <div key={acct.id} className={`glass-card p-3 ${acct.is_archived ? "opacity-50" : ""}`}>
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  {renameAccountId === acct.id ? (
                    <div className="flex gap-1">
                      <input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} className="rounded px-2 py-0.5 text-sm w-40" />
                      <button onClick={() => handleRenameAccount(acct)} className="text-xs px-2 py-0.5 text-white rounded" style={{ backgroundColor: "var(--success)" }}>Save</button>
                      <button onClick={() => setRenameAccountId(null)} className="text-xs px-2 py-0.5 rounded" style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-secondary)" }}>Cancel</button>
                    </div>
                  ) : (
                    <Link to={`/transactions?account_id=${acct.id}`} className="font-medium text-sm hover:underline" style={{ color: "var(--text-primary)" }}>{acct.name}</Link>
                  )}
                  <div className="flex items-center gap-1.5 text-xs mt-0.5">
                    <span className="px-1.5 py-0.5 rounded font-medium" style={{
                      backgroundColor: acct.blockchain && acct.blockchain !== "unknown" ? "var(--bg-surface-hover)" : "transparent",
                      border: acct.blockchain && acct.blockchain !== "unknown" ? "none" : "1px dashed var(--border-default)",
                      color: acct.blockchain && acct.blockchain !== "unknown" ? "var(--text-secondary)" : "var(--text-muted)",
                      fontSize: 11,
                    }}>
                      {acct.blockchain && acct.blockchain !== "unknown" ? acct.blockchain.charAt(0).toUpperCase() + acct.blockchain.slice(1) : "Unknown chain"}
                    </span>
                    {acct.address ? (
                      <span className="font-mono" style={{ color: "var(--text-muted)" }}>
                        {acct.address.length > 20 ? `${acct.address.slice(0, 10)}...${acct.address.slice(-6)}` : acct.address}
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>No address set</span>
                    )}
                  </div>
                  {acct.last_synced_at && (
                    <div className="text-xs mt-0.5" style={{ color: "var(--success)" }}>Synced {timeAgo(acct.last_synced_at)}</div>
                  )}
                  {editAddressAccountId === acct.id && (
                    <div className="mt-2 p-2 rounded" style={{ background: "var(--bg-surface-hover)" }}>
                      <div className="grid grid-cols-2 gap-2 mb-2">
                        <div>
                          <label className="text-xs block mb-0.5" style={{ color: "var(--text-muted)" }}>Blockchain</label>
                          <select value={editBlockchainValue} onChange={(e) => setEditBlockchainValue(e.target.value)} className="rounded px-2 py-1 text-sm w-full">
                            {BLOCKCHAINS.map((b) => <option key={b} value={b}>{b.charAt(0).toUpperCase() + b.slice(1)}</option>)}
                          </select>
                        </div>
                        <div>
                          <label className="text-xs block mb-0.5" style={{ color: "var(--text-muted)" }}>Address</label>
                          <input
                            value={editAddressValue}
                            onChange={(e) => {
                              setEditAddressValue(e.target.value);
                              const detected = detectBlockchain(e.target.value);
                              if (detected) setEditBlockchainValue(detected);
                            }}
                            placeholder="bc1q..." className="rounded px-2 py-1 text-sm w-full font-mono"
                          />
                        </div>
                      </div>
                      <div className="flex gap-1">
                        <button onClick={() => handleSaveAddress(acct)} className="text-xs px-2 py-0.5 text-white rounded" style={{ backgroundColor: "var(--success)" }}>Save</button>
                        <button onClick={() => setEditAddressAccountId(null)} className="text-xs px-2 py-0.5 rounded" style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-secondary)" }}>Cancel</button>
                      </div>
                    </div>
                  )}
                  {moveAccountId === acct.id && (
                    <div className="mt-2 p-2 rounded" style={{ background: "var(--bg-surface-hover)" }}>
                      <div className="text-xs mb-1.5" style={{ color: "var(--text-secondary)" }}>Move to wallet:</div>
                      <div className="flex gap-1.5 items-center">
                        <select value={moveTargetWalletId} onChange={(e) => setMoveTargetWalletId(e.target.value)} className="rounded px-2 py-1 text-sm flex-1" style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-primary)", border: "1px solid var(--border-default)" }}>
                          <option value="">Select wallet...</option>
                          {allWallets.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                        </select>
                        <button onClick={handleMoveAccount} disabled={!moveTargetWalletId || moveLoading} className="text-xs px-2 py-1 text-white rounded disabled:opacity-50" style={{ backgroundColor: "var(--accent)" }}>
                          {moveLoading ? "Moving..." : "Move"}
                        </button>
                        <button onClick={() => setMoveAccountId(null)} className="text-xs px-2 py-0.5 rounded" style={{ backgroundColor: "var(--bg-surface-hover)", color: "var(--text-secondary)" }}>Cancel</button>
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => handleSyncAccount(acct)} disabled={syncingAccountId === acct.id} className="text-xs px-2 py-1 text-white rounded disabled:opacity-50 transition-colors" style={{ backgroundColor: "var(--accent)" }}>
                    {syncingAccountId === acct.id ? "Syncing..." : "Sync"}
                  </button>
                  <DropdownMenu
                    items={[
                      { label: "Rename", onClick: () => { setRenameAccountId(acct.id); setRenameValue(acct.name); } },
                      { label: "Edit Address", onClick: () => { setEditAddressAccountId(acct.id); setEditAddressValue(acct.address || ""); setEditBlockchainValue(acct.blockchain || ""); } },
                      { label: "Move to Wallet", onClick: () => openMoveAccount(acct) },
                      { label: acct.is_archived ? "Unarchive" : "Archive", onClick: () => handleArchiveAccount(acct) },
                      { label: "Delete", onClick: () => handleDeleteAccount(acct), variant: "danger" },
                    ]}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {accountSyncResult && (
        <div className="bg-success-subtle rounded-lg p-3 text-sm" style={{ border: "1px solid rgba(34, 197, 94, 0.2)" }}>
          <div className="font-medium mb-1" style={{ color: "var(--success)" }}>Sync Complete</div>
          <div className="flex gap-4 text-sm">
            <span style={{ color: "var(--success)" }}>{accountSyncResult.imported} imported</span>
            <span style={{ color: "var(--text-muted)" }}>{accountSyncResult.skipped} skipped</span>
            {accountSyncResult.errors > 0 && <span style={{ color: "var(--danger)" }}>{accountSyncResult.errors} errors</span>}
          </div>
        </div>
      )}
    </div>
  );
}
