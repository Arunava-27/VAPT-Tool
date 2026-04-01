import React, { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  NodeProps,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Monitor, Router, Server, Smartphone, Printer, Wifi,
  HelpCircle, Shield, Info
} from 'lucide-react'
import { TopologyNode, TopologyEdge } from '../../api/network'

// ─── Device icon helper ────────────────────────────────────────────────────

function DeviceIcon({ type, className }: { type: string; className?: string }) {
  const cls = className || 'w-5 h-5'
  switch (type) {
    case 'router':  return <Router className={cls} />
    case 'server':  return <Server className={cls} />
    case 'mobile':  return <Smartphone className={cls} />
    case 'printer': return <Printer className={cls} />
    case 'iot':     return <Wifi className={cls} />
    case 'pc':      return <Monitor className={cls} />
    default:        return <HelpCircle className={cls} />
  }
}

// ─── Risk colour helper ────────────────────────────────────────────────────

function riskColor(score: number): { bg: string; border: string; text: string } {
  if (score >= 70) return { bg: 'bg-red-900/80',    border: 'border-red-500',    text: 'text-red-300' }
  if (score >= 40) return { bg: 'bg-orange-900/80', border: 'border-orange-500', text: 'text-orange-300' }
  if (score >= 10) return { bg: 'bg-yellow-900/80', border: 'border-yellow-500', text: 'text-yellow-300' }
  return              { bg: 'bg-slate-800/90',   border: 'border-slate-600',  text: 'text-slate-300' }
}

// ─── Custom node ───────────────────────────────────────────────────────────

function DeviceNode({ data }: NodeProps) {
  const n = (data as unknown) as TopologyNode & { active?: boolean; selected?: boolean }
  const colors = n.is_gateway
    ? { bg: 'bg-blue-900/90', border: 'border-blue-400', text: 'text-blue-200' }
    : n.is_host
      ? { bg: 'bg-emerald-900/90', border: 'border-emerald-400', text: 'text-emerald-200' }
      : riskColor(n.risk_score)

  const riskBadge = !n.is_gateway && !n.is_host && n.risk_score > 0 ? (
    <span className={`text-[9px] font-bold px-1 rounded ${
      n.risk_score >= 70 ? 'bg-red-600' :
      n.risk_score >= 40 ? 'bg-orange-600' :
      n.risk_score >= 10 ? 'bg-yellow-600' : 'bg-slate-600'
    } text-white`}>
      {n.risk_score}
    </span>
  ) : null

  return (
    <div className={`
      relative rounded-xl border-2 px-3 py-2 min-w-[130px] max-w-[160px]
      cursor-pointer transition-all duration-200 select-none
      ${colors.bg} ${colors.border}
      ${n.selected ? 'ring-2 ring-yellow-400 ring-offset-2 ring-offset-slate-900 scale-105 shadow-lg shadow-yellow-900/30' : ''}
      ${!n.selected && n.active ? 'ring-2 ring-cyan-400 ring-offset-1 ring-offset-slate-900' : ''}
    `}>
      <Handle type="target" position={Position.Top}    className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-0 !h-0" />

      <div className="flex items-center gap-1.5 mb-1">
        <span className={colors.text}>
          {n.is_gateway ? <Router className="w-4 h-4" /> :
           n.is_host    ? <Shield className="w-4 h-4" /> :
           <DeviceIcon type={n.device_type} className="w-4 h-4" />}
        </span>
        <span className={`text-xs font-semibold truncate ${colors.text}`}>
          {n.ip}
        </span>
        {riskBadge}
      </div>

      {n.hostname && n.hostname !== 'Gateway / Router' && (
        <p className="text-[10px] text-slate-400 truncate">{n.hostname}</p>
      )}
      {n.is_gateway && (
        <p className="text-[10px] text-blue-400">Gateway / Router</p>
      )}
      {n.is_host && (
        <p className="text-[10px] text-emerald-400">This Machine</p>
      )}

      {n.open_ports && n.open_ports.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-0.5">
          {(n.open_ports as number[]).slice(0, 4).map((p: number) => (
            <span key={p} className="text-[9px] bg-slate-700 text-slate-300 px-1 rounded">
              {p}
            </span>
          ))}
          {n.open_ports.length > 4 && (
            <span className="text-[9px] text-slate-500">+{n.open_ports.length - 4}</span>
          )}
        </div>
      )}

      {n.selected && (
        <div className="absolute -top-1.5 -right-1.5 w-3 h-3 rounded-full bg-yellow-400 flex items-center justify-center">
          <div className="w-1.5 h-1.5 rounded-full bg-yellow-900" />
        </div>
      )}
      {!n.selected && n.active && (
        <div className="absolute -top-1.5 -right-1.5 w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
      )}
    </div>
  )
}

const nodeTypes = { device: DeviceNode, gateway: DeviceNode, host: DeviceNode }

// ─── Radial layout ─────────────────────────────────────────────────────────

function computeLayout(
  tNodes: TopologyNode[],
  activeIps: Set<string>,
  selectedIp?: string,
): Node[] {
  const gw     = tNodes.find(n => n.is_gateway)
  const others = tNodes.filter(n => !n.is_gateway)
  const total  = others.length
  const radius = Math.max(220, total * 38)

  const rfNodes: Node[] = []
  if (gw) {
    rfNodes.push({
      id: gw.id, type: 'gateway',
      position: { x: 0, y: 0 },
      data: { ...gw, active: activeIps.has(gw.ip), selected: selectedIp === gw.ip },
    })
  }
  others.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(total, 1) - Math.PI / 2
    rfNodes.push({
      id: n.id, type: n.type,
      position: { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius },
      data: { ...n, active: activeIps.has(n.ip), selected: selectedIp === n.ip },
    })
  })
  return rfNodes
}

// ─── Props & component ─────────────────────────────────────────────────────

interface TopologyMapProps {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
  activeIps?: Set<string>
  selectedIp?: string
  onNodeClick?: (n: TopologyNode) => void
}

export default function TopologyMap({
  nodes: tNodes,
  edges: tEdges,
  activeIps = new Set(),
  selectedIp,
  onNodeClick,
}: TopologyMapProps) {
  const initialNodes = useMemo(
    () => computeLayout(tNodes, activeIps, selectedIp),
    // recompute only when node set, active ips, or selection changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tNodes.map(n => n.id).join(','), [...activeIps].join(','), selectedIp]
  )

  const rfEdges: Edge[] = useMemo(() => tEdges.map(e => {
    const srcIp = tNodes.find(n => n.id === e.source)?.ip || ''
    const isActive = activeIps.has(srcIp)
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      animated: isActive,
      style: { stroke: isActive ? '#22d3ee' : '#475569', strokeWidth: 1.5 },
    }
  }), [tEdges, tNodes, activeIps])

  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(rfEdges)

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    const original = tNodes.find(n => n.id === node.id)
    if (original && onNodeClick) onNodeClick(original)
  }, [tNodes, onNodeClick])

  if (tNodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500">
        <div className="text-center">
          <Info className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No nodes discovered yet.</p>
          <p className="text-xs mt-1">Run a network discovery to populate the topology.</p>
        </div>
      </div>
    )
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      fitView
      fitViewOptions={{ padding: 0.25 }}
      minZoom={0.25}
      maxZoom={2}
      colorMode="dark"
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1e293b" />
      <Controls className="!bg-slate-800 !border-slate-600 !rounded-lg" />
      <MiniMap
        className="!bg-slate-900 !border-slate-700 !rounded-lg"
        nodeColor={n => {
          const orig = tNodes.find(t => t.id === n.id)
          if (!orig) return '#475569'
          if (orig.is_gateway) return '#60a5fa'
          if (orig.is_host)    return '#34d399'
          const s = orig.risk_score
          return s >= 70 ? '#ef4444' : s >= 40 ? '#f97316' : s >= 10 ? '#eab308' : '#64748b'
        }}
        maskColor="rgba(15,23,42,0.7)"
      />
    </ReactFlow>
  )
}
