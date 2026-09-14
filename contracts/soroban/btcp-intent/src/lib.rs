#![no_std]
use soroban_sdk::{contract, contracterror, contractimpl, contracttype, Env, Address, Map, Symbol, BytesN};

#[contracttype] #[derive(Clone, Debug, PartialEq)]
pub struct Record { pub entity_id: BytesN<32>, pub data_hash: BytesN<32>, pub status: u32, pub created: u32, pub submitter: Address }

#[contracterror] #[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum Error { NotFound=1, NotOwner=2, BadInput=3, AlreadyExists=4 }

const KEY_DATA: Symbol = Symbol::short("data"); const KEY_OWNER: Symbol = Symbol::short("owner");

#[contract] pub struct GenericContract;
#[contractimpl]
impl GenericContract {
    pub fn init(env: Env, owner: Address) { env.storage().instance().set(&KEY_OWNER, &owner); }
    pub fn register(env: Env, id: BytesN<32>, entity_id: BytesN<32>, data_hash: BytesN<32>) -> Result<bool, Error> {
        let mut m: Map<BytesN<32>, Record> = env.storage().persistent().get(&KEY_DATA).unwrap_or_else(|| Map::new(&env));
        if m.contains_key(id.clone()) { return Err(Error::AlreadyExists); }
        m.set(id, Record { entity_id, data_hash, status: 0, created: env.ledger().sequence(), submitter: env.current_contract_address() });
        env.storage().persistent().set(&KEY_DATA, &m); Ok(true)
    }
    pub fn update_status(env: Env, invoker: Address, id: BytesN<32>, status: u32) -> Result<bool, Error> {
        invoker.require_auth(); let owner: Address = env.storage().instance().get(&KEY_OWNER).unwrap(); if invoker != owner { return Err(Error::NotOwner); }
        let mut m: Map<BytesN<32>, Record> = env.storage().persistent().get(&KEY_DATA).unwrap_or_else(|| Map::new(&env));
        let mut r = match m.get(id.clone()) { Some(r) => r, None => return Err(Error::NotFound) };
        r.status = status; m.set(id, r); env.storage().persistent().set(&KEY_DATA, &m); Ok(true)
    }
    pub fn get(env: Env, id: BytesN<32>) -> Option<Record> { let m: Map<BytesN<32>, Record> = env.storage().persistent().get(&KEY_DATA).unwrap_or_else(|| Map::new(&env)); m.get(id) }
}
