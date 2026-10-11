import {mutate} from './storage.mjs';
import {personEdit,nextPerson,ackPerson,peoplePage} from './people-model.mjs';
export const editPerson=(owner,id,role,favorite)=>mutate(owner,w=>personEdit(w,id,role,favorite));
export const next=(owner)=>mutate(owner,nextPerson);
export const acknowledge=(owner,operation,reply)=>mutate(owner,w=>ackPerson(w,operation,reply));
export const page=(owner,value)=>mutate(owner,w=>peoplePage(w,value));
