#![no_std]
use soroban_sdk::{contract, contracterror, contractimpl, contracttype, Env, Vec, BytesN, Bytes, Address, Map, Symbol};

#[contracttype]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BlockHeader { pub height: u64, pub merkle_root: BytesN<32>, pub timestamp: u64, pub bits: u32, pub prev_hash: BytesN<32> }

#[contracttype]
#[derive(Clone, Debug, PartialEq)]
pub struct VerifyArgs { pub block_hash: BytesN<32>, pub txid: BytesN<32>, pub merkle_path: Vec<BytesN<32>>, pub merkle_is_left: Vec<bool>, pub anchor_bh: BytesN<32> }

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum Error { UnknownBlock=1, BlockAboveTip=2, DepthInsufficient=3, BadMerkleProof=4, NotOwner=6, GenesisRenounced=7, AlreadyExists=8, BadInput=9, GenesisNotSet=10, DepthUnsupported=11 }

const KEY_TIP: Symbol = Symbol::short("tip"); const KEY_HDRS: Symbol = Symbol::short("hdrs"); const KEY_OWNER: Symbol = Symbol::short("owner"); const KEY_REN: Symbol = Symbol::short("renounced"); const KEY_TS: Symbol = Symbol::short("tipset"); const KEY_TH: Symbol = Symbol::short("tiph");

#[contract]
pub struct BTCSPVVerifier;

#[contractimpl]
impl BTCSPVVerifier {
    pub fn init(env: Env, owner: Address) { env.storage().instance().set(&KEY_OWNER, &owner); env.storage().instance().set(&KEY_REN, &false); env.storage().instance().set(&KEY_TS, &false); }
    pub fn submit_genesis_tip(env: Env, invoker: Address, block_hash: BytesN<32>, height: u64, merkle_root: BytesN<32>, timestamp: u64, bits: u32) -> Result<bool, Error> {
        invoker.require_auth(); let owner: Address = env.storage().instance().get(&KEY_OWNER).unwrap(); if invoker != owner { return Err(Error::NotOwner); }
        if env.storage().instance().get(&KEY_REN).unwrap_or(false) { return Err(Error::GenesisRenounced); }
        if env.storage().instance().get(&KEY_TS).unwrap_or(false) { return Err(Error::AlreadyExists); }
        if height == 0 { return Err(Error::BadInput); }
        let header = BlockHeader { height, merkle_root, timestamp, bits, prev_hash: BytesN::from_array(&env, &[0u8; 32]) };
        let mut hdrs: Map<BytesN<32>, BlockHeader> = env.storage().persistent().get(&KEY_HDRS).unwrap_or_else(|| Map::new(&env)); hdrs.set(block_hash.clone(), header); env.storage().persistent().set(&KEY_HDRS, &hdrs);
        env.storage().instance().set(&KEY_TIP, &block_hash); env.storage().instance().set(&KEY_TH, &height); env.storage().instance().set(&KEY_TS, &true); Ok(true)
    }
    pub fn submit_block_header(env: Env, invoker: Address, block_hash: BytesN<32>, height: u64, merkle_root: BytesN<32>, timestamp: u64, bits: u32, prev_hash: BytesN<32>) -> Result<bool, Error> {
        invoker.require_auth(); let owner: Address = env.storage().instance().get(&KEY_OWNER).unwrap(); if invoker != owner { return Err(Error::NotOwner); }
        if !env.storage().instance().get(&KEY_TS).unwrap_or(false) { return Err(Error::GenesisNotSet); }
        let tip: BytesN<32> = env.storage().instance().get(&KEY_TIP).unwrap(); let tip_h: u64 = env.storage().instance().get(&KEY_TH).unwrap();
        if prev_hash != tip { return Err(Error::BadInput); } if height != tip_h + 1 { return Err(Error::BadInput); }
        let mut hdrs: Map<BytesN<32>, BlockHeader> = env.storage().persistent().get(&KEY_HDRS).unwrap_or_else(|| Map::new(&env)); if hdrs.contains_key(block_hash.clone()) { return Err(Error::AlreadyExists); }
        hdrs.set(block_hash.clone(), BlockHeader { height, merkle_root, timestamp, bits, prev_hash }); env.storage().persistent().set(&KEY_HDRS, &hdrs);
        env.storage().instance().set(&KEY_TIP, &block_hash); env.storage().instance().set(&KEY_TH, &height); Ok(true)
    }
    pub fn renounce_genesis_ability(env: Env, invoker: Address) -> Result<bool, Error> { invoker.require_auth(); let owner: Address = env.storage().instance().get(&KEY_OWNER).unwrap(); if invoker != owner { return Err(Error::NotOwner); } env.storage().instance().set(&KEY_REN, &true); Ok(true) }
    pub fn verify_anchor(env: Env, args: VerifyArgs) -> Result<bool, Error> {
        let hdrs: Map<BytesN<32>, BlockHeader> = env.storage().persistent().get(&KEY_HDRS).unwrap_or_else(|| Map::new(&env));
        let hdr = match hdrs.get(args.block_hash) { Some(h) => h, None => return Err(Error::UnknownBlock) };
        let tip_h: u64 = env.storage().instance().get(&KEY_TH).unwrap(); if tip_h < hdr.height { return Err(Error::BlockAboveTip); }
        if tip_h - hdr.height < 6 { return Err(Error::DepthInsufficient); }
        let md = args.merkle_path.len(); if md == 0 || md > 24 { return Err(Error::DepthUnsupported); }
        let mut current: Bytes = args.txid.into();
        for i in 0..md { let sib: Bytes = args.merkle_path.get(i).unwrap().into(); let il = args.merkle_is_left.get(i).unwrap_or(false); let mut c = Bytes::new(&env); if il { c.append(&current); c.append(&sib); } else { c.append(&sib); c.append(&current); } let h1: Bytes = env.crypto().sha256(&c).into(); current = env.crypto().sha256(&h1).into(); }
        let rm: Bytes = hdr.merkle_root.clone().into(); if current != rm { return Err(Error::BadMerkleProof); } Ok(true)
    }
    pub fn get_chain_tip(env: Env) -> (BytesN<32>, u64, bool) { let t: BytesN<32> = env.storage().instance().get(&KEY_TIP).unwrap_or_else(|| BytesN::from_array(&env, &[0u8; 32])); let h: u64 = env.storage().instance().get(&KEY_TH).unwrap_or(0); let s: bool = env.storage().instance().get(&KEY_TS).unwrap_or(false); (t, h, s) }
    pub fn block_exists(env: Env, bh: BytesN<32>) -> bool { let hdrs: Map<BytesN<32>, BlockHeader> = env.storage().persistent().get(&KEY_HDRS).unwrap_or_else(|| Map::new(&env)); hdrs.contains_key(bh) }
    pub fn genesis_renounced(env: Env) -> bool { env.storage().instance().get(&KEY_REN).unwrap_or(false) }
    pub fn get_owner(env: Env) -> Address { env.storage().instance().get(&KEY_OWNER).unwrap() }
}
